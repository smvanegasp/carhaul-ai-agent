# One table for everything (keys documented in agent/src/mia/records.py): call records and the
# call list (written by the agent worker), feedback and rate-limit counters (written by the
# API), and the CarHauler catalog snapshot the worker starts from.
resource "aws_dynamodb_table" "main" {
  name                        = local.name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  # Rate-limit counters expire on their own.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}
