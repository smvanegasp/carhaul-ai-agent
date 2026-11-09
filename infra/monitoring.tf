# Email alerts: the API failing, the voice worker down or erroring, call records not saved.
# Free at this size (CloudWatch's first 10 alarms and metrics, SNS's first 1,000 emails).

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

# AWS emails a confirmation link first; alerts only arrive after it's clicked.
resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-errors"
  alarm_description   = "The API answered with 5 or more server errors in 5 minutes."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.api.id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name}-api-crashing"
  alarm_description   = "The API function crashed or timed out (for example it can't start: missing SSM secret)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ECS reports the service's CPU every minute while a worker runs; no data means no worker
# (crash loop, missing secret, image pull failure). Off when agent_count is 0 on purpose.
resource "aws_cloudwatch_metric_alarm" "agent_down" {
  count               = var.agent_count > 0 ? 1 : 0
  alarm_name          = "${local.name}-agent-down"
  alarm_description   = "No voice worker has been running for 10 minutes: nobody can call Mia. Check the ECS service events and /ecs/${local.name}-agent logs."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = aws_ecs_cluster.main.name, ServiceName = aws_ecs_service.agent.name }
  statistic           = "SampleCount"
  period              = 300
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

locals {
  # Logged by the worker (JSON lines in `start` mode): any ERROR, and call records not saved
  # (agent/src/mia/records.py).
  agent_signals = {
    AgentErrors      = "{ $.level = \"ERROR\" }"
    RecordSaveFailed = "\"couldn't save the call record\""
  }
}

resource "aws_cloudwatch_log_metric_filter" "agent" {
  for_each       = local.agent_signals
  name           = each.key
  log_group_name = aws_cloudwatch_log_group.agent.name
  pattern        = each.value

  metric_transformation {
    name          = each.key
    namespace     = "CarHaul"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "agent_errors" {
  alarm_name          = "${local.name}-agent-errors"
  alarm_description   = "The voice worker logged 3+ errors in 15 minutes (a provider down, a key revoked or a spend limit hit). Check /ecs/${local.name}-agent."
  namespace           = "CarHaul"
  metric_name         = "AgentErrors"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.agent]
}

resource "aws_cloudwatch_metric_alarm" "record_save_failed" {
  alarm_name          = "${local.name}-call-record-not-saved"
  alarm_description   = "A call record couldn't be saved to DynamoDB (the dashboard will miss that call)."
  namespace           = "CarHaul"
  metric_name         = "RecordSaveFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.agent]
}
