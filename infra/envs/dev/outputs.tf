# ============================================================================
# Kinesis Outputs
# ============================================================================
output "kinesis_stream_name" {
  description = "Name of the Kinesis data stream"
  value       = var.enable_kinesis ? aws_kinesis_stream.transactions[0].name : null
}

output "kinesis_stream_arn" {
  description = "ARN of the Kinesis data stream"
  value       = var.enable_kinesis ? aws_kinesis_stream.transactions[0].arn : null
}

# ============================================================================
# Lambda Outputs
# ============================================================================
output "lambda_function_name" {
  description = "Name of the Lambda fraud scorer function"
  value       = var.enable_lambda ? aws_lambda_function.fraud_scorer[0].function_name : null
}

output "lambda_function_arn" {
  description = "ARN of the Lambda fraud scorer function"
  value       = var.enable_lambda ? aws_lambda_function.fraud_scorer[0].arn : null
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = var.enable_lambda ? aws_iam_role.lambda[0].arn : null
}

output "lambda_dlq_url" {
  description = "URL of the Lambda dead letter queue"
  value       = var.enable_lambda ? aws_sqs_queue.lambda_dlq[0].url : null
}

# ============================================================================
# S3 Outputs
# ============================================================================
output "s3_raw_bucket_name" {
  description = "Name of the raw data S3 bucket"
  value       = aws_s3_bucket.raw.id
}

output "s3_raw_bucket_arn" {
  description = "ARN of the raw data S3 bucket"
  value       = aws_s3_bucket.raw.arn
}

output "s3_enriched_bucket_name" {
  description = "Name of the enriched data S3 bucket"
  value       = aws_s3_bucket.enriched.id
}

output "s3_enriched_bucket_arn" {
  description = "ARN of the enriched data S3 bucket"
  value       = aws_s3_bucket.enriched.arn
}

# ============================================================================
# Glue Outputs
# ============================================================================
output "glue_database_name" {
  description = "Name of the Glue catalog database"
  value       = aws_glue_catalog_database.fraud_analytics.name
}

output "glue_raw_table_name" {
  description = "Name of the Glue catalog table for raw transactions"
  value       = aws_glue_catalog_table.raw_transactions.name
}

output "glue_enriched_table_name" {
  description = "Name of the Glue catalog table for enriched transactions"
  value       = aws_glue_catalog_table.enriched_transactions.name
}

# ============================================================================
# Redshift Outputs
# ============================================================================
output "redshift_namespace_id" {
  description = "ID of the Redshift Serverless namespace"
  value       = var.enable_redshift ? aws_redshiftserverless_namespace.fraud_analytics[0].namespace_id : null
}

output "redshift_workgroup_id" {
  description = "ID of the Redshift Serverless workgroup"
  value       = var.enable_redshift ? aws_redshiftserverless_workgroup.fraud_analytics[0].workgroup_id : null
}

output "redshift_workgroup_endpoint" {
  description = "Endpoint address for the Redshift Serverless workgroup"
  value       = var.enable_redshift ? aws_redshiftserverless_workgroup.fraud_analytics[0].endpoint[0].address : null
}

output "redshift_workgroup_port" {
  description = "Port for the Redshift Serverless workgroup"
  value       = var.enable_redshift ? aws_redshiftserverless_workgroup.fraud_analytics[0].endpoint[0].port : null
}

output "redshift_database_name" {
  description = "Name of the Redshift database"
  value       = var.enable_redshift ? aws_redshiftserverless_namespace.fraud_analytics[0].db_name : null
}

output "redshift_admin_username" {
  description = "Admin username for Redshift"
  value       = var.enable_redshift ? var.redshift_admin_username : null
}

output "redshift_admin_password_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Redshift admin password"
  value       = var.enable_redshift ? aws_secretsmanager_secret.redshift_admin[0].arn : null
  sensitive   = true
}

output "redshift_role_arn" {
  description = "ARN of the Redshift IAM role"
  value       = var.enable_redshift ? aws_iam_role.redshift[0].arn : null
}

output "redshift_usage_limit_id" {
  description = "ID of the Redshift usage limit (cost guardrail)"
  value       = var.enable_redshift ? aws_redshiftserverless_usage_limit.monthly_rpu_hours[0].id : null
}

# ============================================================================
# KMS Outputs
# ============================================================================
output "kms_key_id" {
  description = "ID of the KMS key for data encryption"
  value       = aws_kms_key.data_encryption.key_id
}

output "kms_key_arn" {
  description = "ARN of the KMS key for data encryption"
  value       = aws_kms_key.data_encryption.arn
}

# ============================================================================
# CloudWatch Outputs
# ============================================================================
output "lambda_log_group_name" {
  description = "Name of the Lambda CloudWatch log group"
  value       = var.enable_lambda ? aws_cloudwatch_log_group.lambda[0].name : null
}

output "redshift_log_group_name" {
  description = "Name of the Redshift CloudWatch log group"
  value       = var.enable_redshift ? aws_cloudwatch_log_group.redshift[0].name : null
}

output "sns_alarms_topic_arn" {
  description = "ARN of the SNS topic for CloudWatch alarms"
  value       = var.enable_cloudwatch_alarms ? aws_sns_topic.alarms[0].arn : null
}

# ============================================================================
# Kinesis Firehose Outputs
# ============================================================================
output "firehose_delivery_stream_name" {
  description = "Name of the Kinesis Firehose delivery stream"
  value       = var.enable_kinesis ? aws_kinesis_firehose_delivery_stream.transactions[0].name : null
}

output "firehose_delivery_stream_arn" {
  description = "ARN of the Kinesis Firehose delivery stream"
  value       = var.enable_kinesis ? aws_kinesis_firehose_delivery_stream.transactions[0].arn : null
}

# ============================================================================
# DynamoDB Outputs
# ============================================================================
output "dynamodb_metrics_table_name" {
  description = "Name of the DynamoDB metrics table"
  value       = aws_dynamodb_table.metrics.name
}

output "dynamodb_metrics_table_arn" {
  description = "ARN of the DynamoDB metrics table"
  value       = aws_dynamodb_table.metrics.arn
}

output "dynamodb_latest_state_table_name" {
  description = "Name of the DynamoDB latest_state table"
  value       = aws_dynamodb_table.latest_state.name
}

output "dynamodb_latest_state_table_arn" {
  description = "ARN of the DynamoDB latest_state table"
  value       = aws_dynamodb_table.latest_state.arn
}

# ============================================================================
# EventBridge Outputs
# ============================================================================
output "eventbridge_daily_load_rule_name" {
  description = "Name of the EventBridge rule for daily Redshift loads"
  value       = aws_cloudwatch_event_rule.daily_load.name
}

output "eventbridge_role_arn" {
  description = "ARN of the EventBridge IAM role"
  value       = aws_iam_role.eventbridge.arn
}

# ============================================================================
# General Outputs
# ============================================================================
output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "project_name" {
  description = "Project name"
  value       = var.project_name
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "aws_account_id" {
  description = "AWS account ID"
  value       = local.account_id
}
