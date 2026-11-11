# The FastAPI backend: the backend/Dockerfile "lambda" stage on Lambda, behind an HTTP API.

resource "aws_ecr_repository" "api" {
  name = "${local.name}-api"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy     = local.keep_last_images
}

locals {
  # ECR storage is billed per GB-month and the worker image is ~1.6 GB: keep only 2 per repo.
  keep_last_images = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 2 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 2 }
      action       = { type = "expire" }
    }]
  })
}

# scripts/deploy.sh pushes ":latest"; pinning the digest makes Lambda update when it changes.
data "aws_ecr_image" "api" {
  repository_name = aws_ecr_repository.api.name
  image_tag       = "latest"
}

# CloudFront sends this header to the API; the app refuses requests without it.
resource "random_password" "origin_secret" {
  length  = 40
  special = false
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = 30
}

resource "aws_iam_role" "api" {
  name = "${local.name}-api"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.main.arn
      },
      {
        # Start the on-demand worker and see whether it's up (backend/app/worker.py).
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = "arn:aws:ecs:us-east-1:${local.account_id}:task-definition/${aws_ecs_task_definition.agent.family}:*"
      },
      {
        Effect    = "Allow"
        Action    = ["ecs:ListTasks", "ecs:DescribeTasks"]
        Resource  = "*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.agent_execution.arn, aws_iam_role.agent_task.arn]
      },
      {
        # Only the API's own secrets (the LiveKit key to mint call tokens), not the worker's.
        # SecureStrings use the AWS-managed aws/ssm key, whose policy already allows SSM use.
        Effect   = "Allow"
        Action   = "ssm:GetParametersByPath"
        Resource = "arn:aws:ssm:us-east-1:${local.account_id}:parameter${local.ssm_prefix}api/"
      },
    ]
  })
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}@${data.aws_ecr_image.api.image_digest}"
  architectures = ["x86_64"]
  memory_size   = 512
  timeout       = 15

  environment {
    variables = {
      TABLE_NAME    = aws_dynamodb_table.main.name
      SSM_PREFIX    = "${local.ssm_prefix}api/"
      ORIGIN_SECRET = random_password.origin_secret.result
      # Every call spends money (Groq, Deepgram, ElevenLabs, LiveKit, CarHauler).
      CALLS_PER_IP_PER_HOUR = tostring(var.calls_per_ip_per_hour)
      CALLS_PER_DAY         = tostring(var.calls_per_day)
      # The on-demand worker it starts and dispatches into calls (infra/agent.tf).
      MIA_AGENT_NAME        = "mia"
      AGENT_CLUSTER         = aws_ecs_cluster.main.name
      AGENT_TASK_FAMILY     = aws_ecs_task_definition.agent.family
      AGENT_SUBNETS         = join(",", data.aws_subnets.default.ids)
      AGENT_SECURITY_GROUP  = aws_security_group.agent.id
      WORKER_STARTS_PER_DAY = tostring(var.worker_starts_per_day)
      # Lambda Web Adapter: wait for uvicorn's port (the HTTP check would need the origin header).
      AWS_LWA_READINESS_CHECK_PROTOCOL = "tcp"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "api" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  # A ceiling for the whole API; per-IP and per-day call limits live in the app.
  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*"
}
