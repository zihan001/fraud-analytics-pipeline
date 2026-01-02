# ============================================================================
# DynamoDB Tables for Live Dashboard (Speed Layer)
# ============================================================================

# Metrics Table: Time-window counters for live dashboard
resource "aws_dynamodb_table" "metrics" {
  name         = "${local.name_prefix}-metrics"
  billing_mode = "PAY_PER_REQUEST" # On-demand for variable load

  hash_key  = "pk"
  range_key = "sk"

  attribute {
    name = "pk"
    type = "S" # metric#{metric_name}
  }

  attribute {
    name = "sk"
    type = "S" # window#{YYYY-MM-DDTHH:MM}
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.data_encryption.arn
  }

  tags = {
    Name        = "${local.name_prefix}-metrics"
    Purpose     = "Live dashboard time-series counters"
    Environment = var.environment
  }
}

# Latest State Table: Most recent state per entity
resource "aws_dynamodb_table" "latest_state" {
  name         = "${local.name_prefix}-latest-state"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "pk"

  attribute {
    name = "pk"
    type = "S" # {entity_type}#{entity_id}
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.data_encryption.arn
  }

  tags = {
    Name        = "${local.name_prefix}-latest-state"
    Purpose     = "Latest entity state for live dashboard"
    Environment = var.environment
  }
}
