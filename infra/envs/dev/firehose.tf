# ============================================================================
# Kinesis Firehose Delivery Stream (Batch Layer)
# ============================================================================

# IAM Role for Firehose
resource "aws_iam_role" "firehose" {
  count = var.enable_kinesis ? 1 : 0

  name = "${local.name_prefix}-firehose-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-firehose-role"
  }
}

# IAM Policy for Firehose
resource "aws_iam_role_policy" "firehose" {
  count = var.enable_kinesis ? 1 : 0

  name = "${local.name_prefix}-firehose-policy"
  role = aws_iam_role.firehose[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:DescribeStream",
          "kinesis:GetShardIterator",
          "kinesis:GetRecords",
          "kinesis:ListShards"
        ]
        Resource = aws_kinesis_stream.transactions[0].arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.data_encryption.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.firehose[0].arn}:*"
      }
    ]
  })
}

# CloudWatch Log Group for Firehose
resource "aws_cloudwatch_log_group" "firehose" {
  count = var.enable_kinesis ? 1 : 0

  name              = "/aws/kinesisfirehose/${local.name_prefix}-transactions"
  retention_in_days = 7
  kms_key_id        = aws_kms_key.data_encryption.arn

  tags = {
    Name = "${local.name_prefix}-firehose-logs"
  }
}

# CloudWatch Log Stream for Firehose
resource "aws_cloudwatch_log_stream" "firehose_s3" {
  count = var.enable_kinesis ? 1 : 0

  name           = "S3Delivery"
  log_group_name = aws_cloudwatch_log_group.firehose[0].name
}

resource "aws_cloudwatch_log_stream" "firehose_errors" {
  count = var.enable_kinesis ? 1 : 0

  name           = "ErrorLogs"
  log_group_name = aws_cloudwatch_log_group.firehose[0].name
}

# Kinesis Firehose Delivery Stream
resource "aws_kinesis_firehose_delivery_stream" "transactions" {
  count = var.enable_kinesis ? 1 : 0

  name        = "${local.name_prefix}-transactions"
  destination = "extended_s3"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.transactions[0].arn
    role_arn           = aws_iam_role.firehose[0].arn
  }

  extended_s3_configuration {
    role_arn            = aws_iam_role.firehose[0].arn
    bucket_arn          = aws_s3_bucket.raw.arn
    prefix              = "raw/dt=!{partitionKeyFromQuery:dt}/hr=!{partitionKeyFromQuery:hr}/"
    error_output_prefix = "raw_errors/dt=!{timestamp:yyyy-MM-dd}/hr=!{timestamp:HH}/!{firehose:error-output-type}/"

    # Buffering hints for optimal file sizing
    buffering_size     = var.firehose_buffer_size_mb
    buffering_interval = var.firehose_buffer_interval_sec

    compression_format = "GZIP"

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose[0].name
      log_stream_name = aws_cloudwatch_log_stream.firehose_s3[0].name
    }

    # Dynamic partitioning configuration
    dynamic_partitioning_configuration {
      enabled = true
    }

    processing_configuration {
      enabled = true

      # Metadata extraction for partitioning
      processors {
        type = "MetadataExtraction"
        parameters {
          parameter_name  = "MetadataExtractionQuery"
          parameter_value = "{dt:.event_ts[0:10],hr:.event_ts[11:13]}"
        }
        parameters {
          parameter_name  = "JsonParsingEngine"
          parameter_value = "JQ-1.6"
        }
      }

      # AppendDelimiterToRecord for JSON Lines format
      processors {
        type = "AppendDelimiterToRecord"
        parameters {
          parameter_name  = "Delimiter"
          parameter_value = "\\n"
        }
      }
    }
  }

  tags = {
    Name        = "${local.name_prefix}-firehose"
    Purpose     = "Batch layer S3 ingestion with file buffering"
    Environment = var.environment
  }

  depends_on = [
    aws_iam_role_policy.firehose
  ]
}
