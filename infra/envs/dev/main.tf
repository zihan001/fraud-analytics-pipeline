# Data sources
data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  name_prefix = "${var.project_name}-${var.environment}"
}

# ============================================================================
# KMS Key for Data Encryption
# ============================================================================
resource "aws_kms_key" "data_encryption" {
  description             = "KMS key for ${var.project_name} data encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name = "${local.name_prefix}-data-key"
  }
}

resource "aws_kms_alias" "data_encryption" {
  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.data_encryption.key_id
}

# ============================================================================
# S3 Buckets for Data Lake
# ============================================================================

# Raw Zone Bucket
resource "aws_s3_bucket" "raw" {
  bucket = "${local.name_prefix}-raw-${local.account_id}"

  tags = {
    Name = "${local.name_prefix}-raw"
    Zone = "raw"
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data_encryption.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "expire-raw-data"
    status = "Enabled"

    filter {}

    expiration {
      days = var.s3_raw_expiration_days
    }
  }
}

# Enriched Zone Bucket
resource "aws_s3_bucket" "enriched" {
  bucket = "${local.name_prefix}-enriched-${local.account_id}"

  tags = {
    Name = "${local.name_prefix}-enriched"
    Zone = "enriched"
  }
}

resource "aws_s3_bucket_versioning" "enriched" {
  bucket = aws_s3_bucket.enriched.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "enriched" {
  bucket = aws_s3_bucket.enriched.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data_encryption.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "enriched" {
  bucket = aws_s3_bucket.enriched.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "enriched" {
  bucket = aws_s3_bucket.enriched.id

  rule {
    id     = "transition-to-glacier"
    status = "Enabled"

    filter {}

    transition {
      days          = var.s3_enriched_transition_days
      storage_class = "GLACIER"
    }
  }
}

# ============================================================================
# Kinesis Data Stream
# ============================================================================
resource "aws_kinesis_stream" "transactions" {
  count = var.enable_kinesis ? 1 : 0

  name             = "${local.name_prefix}-transactions"
  shard_count      = var.kinesis_shard_count
  retention_period = var.kinesis_retention_hours

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.data_encryption.id

  shard_level_metrics = [
    "IncomingBytes",
    "IncomingRecords",
    "OutgoingBytes",
    "OutgoingRecords",
  ]

  tags = {
    Name = "${local.name_prefix}-transactions"
  }
}

# ============================================================================
# IAM Role for Lambda
# ============================================================================
resource "aws_iam_role" "lambda" {
  count = var.enable_lambda ? 1 : 0

  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-lambda-role"
  }
}

resource "aws_iam_role_policy" "lambda" {
  count = var.enable_lambda ? 1 : 0

  name = "${local.name_prefix}-lambda-policy"
  role = aws_iam_role.lambda[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${local.name_prefix}-*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "kinesis:GetRecords",
          "kinesis:GetShardIterator",
          "kinesis:DescribeStream",
          "kinesis:ListShards",
          "kinesis:ListStreams"
        ]
        Resource = var.enable_kinesis ? aws_kinesis_stream.transactions[0].arn : "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = [
          "${aws_s3_bucket.raw.arn}/*",
          "${aws_s3_bucket.enriched.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.data_encryption.arn
      }
    ]
  })
}

# ============================================================================
# Lambda Function for Fraud Scoring
# ============================================================================
resource "aws_cloudwatch_log_group" "lambda" {
  count = var.enable_lambda ? 1 : 0

  name              = "/aws/lambda/${local.name_prefix}-fraud-scorer"
  retention_in_days = var.cloudwatch_log_retention_days
  kms_key_id        = aws_kms_key.data_encryption.arn

  tags = {
    Name = "${local.name_prefix}-lambda-logs"
  }
}

resource "aws_lambda_function" "fraud_scorer" {
  count = var.enable_lambda ? 1 : 0

  function_name = "${local.name_prefix}-fraud-scorer"
  role          = aws_iam_role.lambda[0].arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  # Placeholder code - will be replaced by actual Lambda deployment
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  environment {
    variables = {
      RAW_BUCKET      = aws_s3_bucket.raw.id
      ENRICHED_BUCKET = aws_s3_bucket.enriched.id
      ENVIRONMENT     = var.environment
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = {
    Name = "${local.name_prefix}-fraud-scorer"
  }
}

# Create placeholder Lambda code
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_placeholder.zip"

  source {
    content  = <<-EOT
      import json
      def lambda_handler(event, context):
          return {'statusCode': 200, 'body': json.dumps('Placeholder - deploy actual code')}
    EOT
    filename = "lambda_function.py"
  }
}

# Lambda Event Source Mapping (Kinesis Trigger)
resource "aws_lambda_event_source_mapping" "kinesis" {
  count = var.enable_lambda && var.enable_kinesis ? 1 : 0

  event_source_arn  = aws_kinesis_stream.transactions[0].arn
  function_name     = aws_lambda_function.fraud_scorer[0].arn
  starting_position = "LATEST"
  batch_size        = var.lambda_batch_size

  maximum_batching_window_in_seconds = 5
  parallelization_factor             = 1

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.lambda_dlq[0].arn
    }
  }
}

# Dead Letter Queue for Lambda
resource "aws_sqs_queue" "lambda_dlq" {
  count = var.enable_lambda ? 1 : 0

  name                       = "${local.name_prefix}-lambda-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 300

  kms_master_key_id = aws_kms_key.data_encryption.id

  tags = {
    Name = "${local.name_prefix}-lambda-dlq"
  }
}

resource "aws_sqs_queue_policy" "lambda_dlq" {
  count = var.enable_lambda ? 1 : 0

  queue_url = aws_sqs_queue.lambda_dlq[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.lambda_dlq[0].arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_lambda_function.fraud_scorer[0].arn
          }
        }
      }
    ]
  })
}

# ============================================================================
# AWS Glue Data Catalog
# ============================================================================
resource "aws_glue_catalog_database" "fraud_analytics" {
  name = "${var.project_name}_${var.environment}"

  description = "Data catalog for ${var.project_name} ${var.environment} environment"
}

resource "aws_glue_catalog_table" "raw_transactions" {
  name          = "raw_transactions"
  database_name = aws_glue_catalog_database.fraud_analytics.name

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.raw.id}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "step"
      type = "int"
    }
    columns {
      name = "type"
      type = "string"
    }
    columns {
      name = "amount"
      type = "double"
    }
    columns {
      name = "nameOrig"
      type = "string"
    }
    columns {
      name = "oldbalanceOrg"
      type = "double"
    }
    columns {
      name = "newbalanceOrig"
      type = "double"
    }
    columns {
      name = "nameDest"
      type = "string"
    }
    columns {
      name = "oldbalanceDest"
      type = "double"
    }
    columns {
      name = "newbalanceDest"
      type = "double"
    }
    columns {
      name = "isFraud"
      type = "int"
    }
    columns {
      name = "isFlaggedFraud"
      type = "int"
    }
  }

  partition_keys {
    name = "dt"
    type = "string"
  }
  partition_keys {
    name = "hr"
    type = "string"
  }
}

resource "aws_glue_catalog_table" "enriched_transactions" {
  name          = "enriched_transactions"
  database_name = aws_glue_catalog_database.fraud_analytics.name

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.enriched.id}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "step"
      type = "int"
    }
    columns {
      name = "type"
      type = "string"
    }
    columns {
      name = "amount"
      type = "double"
    }
    columns {
      name = "nameOrig"
      type = "string"
    }
    columns {
      name = "oldbalanceOrg"
      type = "double"
    }
    columns {
      name = "newbalanceOrig"
      type = "double"
    }
    columns {
      name = "nameDest"
      type = "string"
    }
    columns {
      name = "oldbalanceDest"
      type = "double"
    }
    columns {
      name = "newbalanceDest"
      type = "double"
    }
    columns {
      name = "isFraud"
      type = "int"
    }
    columns {
      name = "isFlaggedFraud"
      type = "int"
    }
    columns {
      name = "risk_score"
      type = "double"
    }
    columns {
      name = "risk_level"
      type = "string"
    }
    columns {
      name = "is_flagged"
      type = "boolean"
    }
    columns {
      name = "risk_reasons"
      type = "array<string>"
    }
    columns {
      name = "processed_at"
      type = "timestamp"
    }
  }

  partition_keys {
    name = "dt"
    type = "string"
  }
  partition_keys {
    name = "hr"
    type = "string"
  }
}

# ============================================================================
# Redshift Serverless
# ============================================================================

# Generate random password for Redshift admin
resource "random_password" "redshift_admin" {
  count = var.enable_redshift ? 1 : 0

  length  = 16
  special = true
}

# Store password in Secrets Manager
resource "aws_secretsmanager_secret" "redshift_admin" {
  count = var.enable_redshift ? 1 : 0

  name                    = "${local.name_prefix}-redshift-admin-password"
  recovery_window_in_days = 7
  kms_key_id              = aws_kms_key.data_encryption.id

  tags = {
    Name = "${local.name_prefix}-redshift-admin-password"
  }
}

resource "aws_secretsmanager_secret_version" "redshift_admin" {
  count = var.enable_redshift ? 1 : 0

  secret_id = aws_secretsmanager_secret.redshift_admin[0].id
  secret_string = jsonencode({
    username = var.redshift_admin_username
    password = random_password.redshift_admin[0].result
  })
}

# IAM Role for Redshift
resource "aws_iam_role" "redshift" {
  count = var.enable_redshift ? 1 : 0

  name = "${local.name_prefix}-redshift-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "redshift.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-redshift-role"
  }
}

resource "aws_iam_role_policy" "redshift" {
  count = var.enable_redshift ? 1 : 0

  name = "${local.name_prefix}-redshift-policy"
  role = aws_iam_role.redshift[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.enriched.arn,
          "${aws_s3_bucket.enriched.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions"
        ]
        Resource = [
          "arn:aws:glue:${var.aws_region}:${local.account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${local.account_id}:database/${aws_glue_catalog_database.fraud_analytics.name}",
          "arn:aws:glue:${var.aws_region}:${local.account_id}:table/${aws_glue_catalog_database.fraud_analytics.name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.data_encryption.arn
      }
    ]
  })
}

# Redshift Serverless Namespace
resource "aws_redshiftserverless_namespace" "fraud_analytics" {
  count = var.enable_redshift ? 1 : 0

  namespace_name      = "${local.name_prefix}-namespace"
  admin_username      = var.redshift_admin_username
  admin_user_password = random_password.redshift_admin[0].result
  db_name             = "${var.project_name}_${var.environment}"
  iam_roles           = [aws_iam_role.redshift[0].arn]

  kms_key_id = aws_kms_key.data_encryption.arn

  tags = {
    Name = "${local.name_prefix}-namespace"
  }
}

# Redshift Serverless Workgroup
resource "aws_redshiftserverless_workgroup" "fraud_analytics" {
  count = var.enable_redshift ? 1 : 0

  namespace_name = aws_redshiftserverless_namespace.fraud_analytics[0].namespace_name
  workgroup_name = "${local.name_prefix}-workgroup"
  base_capacity  = var.redshift_base_capacity

  publicly_accessible = false

  tags = {
    Name = "${local.name_prefix}-workgroup"
  }
}

# Redshift Serverless Usage Limit (Cost Guardrail)
resource "aws_redshiftserverless_usage_limit" "monthly_rpu_hours" {
  count = var.enable_redshift ? 1 : 0

  resource_arn  = aws_redshiftserverless_workgroup.fraud_analytics[0].arn
  usage_type    = "serverless-compute"
  amount        = var.redshift_rpu_hour_limit
  period        = "monthly"
  breach_action = "log" # Options: "log" (just alert), "emit-metric", "deactivate" (stop workgroup)
}

# CloudWatch Log Group for Redshift
resource "aws_cloudwatch_log_group" "redshift" {
  count = var.enable_redshift ? 1 : 0

  name              = "/aws/redshift/${local.name_prefix}"
  retention_in_days = var.cloudwatch_log_retention_days
  kms_key_id        = aws_kms_key.data_encryption.arn

  tags = {
    Name = "${local.name_prefix}-redshift-logs"
  }
}

# ============================================================================
# EventBridge Rules for Orchestration
# ============================================================================

# IAM Role for EventBridge
resource "aws_iam_role" "eventbridge" {
  name = "${local.name_prefix}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-eventbridge-role"
  }
}

# Schedule for daily Redshift load (at 2 AM)
resource "aws_cloudwatch_event_rule" "daily_load" {
  name                = "${local.name_prefix}-daily-redshift-load"
  description         = "Trigger daily S3 to Redshift load"
  schedule_expression = "cron(0 2 * * ? *)"

  tags = {
    Name = "${local.name_prefix}-daily-load-rule"
  }
}

# ============================================================================
# CloudWatch Alarms
# ============================================================================

# SNS Topic for alarms
resource "aws_sns_topic" "alarms" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  name              = "${local.name_prefix}-alarms"
  kms_master_key_id = aws_kms_key.data_encryption.id

  tags = {
    Name = "${local.name_prefix}-alarms-topic"
  }
}

resource "aws_sns_topic_subscription" "alarms_email" {
  count = var.enable_cloudwatch_alarms && var.alarm_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# Lambda Error Alarm
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.enable_cloudwatch_alarms && var.enable_lambda ? 1 : 0

  alarm_name          = "${local.name_prefix}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda function error rate is too high"
  alarm_actions       = [aws_sns_topic.alarms[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.fraud_scorer[0].function_name
  }

  tags = {
    Name = "${local.name_prefix}-lambda-error-alarm"
  }
}

# Lambda Throttle Alarm
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  count = var.enable_cloudwatch_alarms && var.enable_lambda ? 1 : 0

  alarm_name          = "${local.name_prefix}-lambda-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Lambda function is being throttled"
  alarm_actions       = [aws_sns_topic.alarms[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.fraud_scorer[0].function_name
  }

  tags = {
    Name = "${local.name_prefix}-lambda-throttle-alarm"
  }
}

# Kinesis Iterator Age Alarm
resource "aws_cloudwatch_metric_alarm" "kinesis_iterator_age" {
  count = var.enable_cloudwatch_alarms && var.enable_kinesis ? 1 : 0

  alarm_name          = "${local.name_prefix}-kinesis-iterator-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IteratorAge"
  namespace           = "AWS/Kinesis"
  period              = 300
  statistic           = "Maximum"
  threshold           = 60000 # 1 minute in milliseconds
  alarm_description   = "Kinesis iterator age is too high - processing lag detected"
  alarm_actions       = [aws_sns_topic.alarms[0].arn]

  dimensions = {
    StreamName = aws_kinesis_stream.transactions[0].name
  }

  tags = {
    Name = "${local.name_prefix}-kinesis-iterator-age-alarm"
  }
}

# DLQ Message Alarm
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  count = var.enable_cloudwatch_alarms && var.enable_lambda ? 1 : 0

  alarm_name          = "${local.name_prefix}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Messages in Lambda DLQ - check for processing failures"
  alarm_actions       = [aws_sns_topic.alarms[0].arn]

  dimensions = {
    QueueName = aws_sqs_queue.lambda_dlq[0].name
  }

  tags = {
    Name = "${local.name_prefix}-dlq-message-alarm"
  }
}
