# The voice worker (agent/Dockerfile) on ECS Fargate, **on demand**: there is no ECS service
# keeping it up. The API starts one task when someone opens the call page (backend/app/worker.py)
# and the worker exits after 10 idle minutes (agent/src/mia/idle.py), so an unused site costs
# nothing and a test session costs cents (1 vCPU / 3 GB is ~$0.06/hour, billed per second).
#
# It keeps a WebSocket open to LiveKit Cloud for every call, so it can't be a Lambda. It only
# connects out (LiveKit, Groq, Deepgram, ElevenLabs, CarHauler, Google): no load balancer and
# no inbound port. It runs in the default VPC's public subnets with a public IP, which avoids a
# NAT gateway (~$32/month).

variable "agent_cpu" {
  description = "Worker vCPU units (1024 = 1 vCPU). Each call runs in its own process."
  type        = number
  default     = 1024
}

variable "agent_memory" {
  description = "Worker memory in MB: each warm process holds the VAD and turn-detector models."
  type        = number
  default     = 3072
}

variable "worker_starts_per_day" {
  description = "How many times a day the API may start the worker (a cost guard)."
  type        = number
  default     = 20
}

resource "aws_ecr_repository" "agent" {
  name = "${local.name}-agent"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name
  policy     = local.keep_last_images
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/ecs/${local.name}-agent"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "main" {
  name = local.name
}

# The worker's secrets, read by ECS when a task starts (scripts/set_aws_secrets.py puts them).
locals {
  agent_secrets = [
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY", "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "CARHAULER_API_KEY", "GOOGLE_MAPS_API_KEY",
  ]
  agent_ssm_arn = "arn:aws:ssm:us-east-1:${local.account_id}:parameter${local.ssm_prefix}agent"
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Used by ECS itself to start the task: pull the image, read the secrets, write logs.
resource "aws_iam_role" "agent_execution" {
  name               = "${local.name}-agent-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "agent_execution" {
  role       = aws_iam_role.agent_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "agent_execution_secrets" {
  role = aws_iam_role.agent_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParameters"
      Resource = [for s in local.agent_secrets : "${local.agent_ssm_arn}/${s}"]
    }]
  })
}

# Used by the worker's code: write call records, read and write the catalog snapshot.
resource "aws_iam_role" "agent_task" {
  name               = "${local.name}-agent-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "agent_task" {
  role = aws_iam_role.agent_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
      Resource = aws_dynamodb_table.main.arn
    }]
  })
}

resource "aws_ecs_task_definition" "agent" {
  family                   = "${local.name}-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.agent_cpu
  memory                   = var.agent_memory
  execution_role_arn       = aws_iam_role.agent_execution.arn
  task_role_arn            = aws_iam_role.agent_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "agent"
    image     = "${aws_ecr_repository.agent.repository_url}:latest"
    essential = true
    # If ECS stops the task, the worker lets current calls finish for up to 2 minutes
    # (Fargate's maximum). Normally it stops itself when idle, with no call running.
    stopTimeout = 120
    environment = [
      { name = "TABLE_NAME", value = aws_dynamodb_table.main.name },
      { name = "AWS_REGION", value = "us-east-1" },
      # Chosen from 5+5 scripted calls (docs/BACKLOG.md, stage 3): same latency as the cloud
      # model, and no per-turn call to LiveKit Inference.
      { name = "MIA_TURN_DETECTOR", value = "v1-mini" },
      { name = "MIA_IDLE_PROCESSES", value = "2" },
      # Exit after 10 minutes with no call and no wake from the call page; 2 hours at most.
      { name = "MIA_IDLE_EXIT_SECONDS", value = "600" },
      { name = "MIA_MAX_UPTIME_SECONDS", value = "7200" },
    ]
    secrets = [for s in local.agent_secrets : { name = s, valueFrom = "${local.agent_ssm_arn}/${s}" }]
    healthCheck = {
      # The worker's own health endpoint: 200 once it's registered with LiveKit.
      command = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8081/', timeout=3)"]
      # Often: the call page waits for HEALTHY before letting the caller call.
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 120
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.agent.name
        awslogs-region        = "us-east-1"
        awslogs-stream-prefix = "agent"
      }
    }
  }])
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "agent" {
  name        = "${local.name}-agent"
  description = "Mia's voice worker: outbound only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "LiveKit (WebSocket and WebRTC) and the model/data APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
