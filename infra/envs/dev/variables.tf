variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "ca-west-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "fraud-analytics"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ============================================================================
# Feature Flags (Cost Control for Portfolio/Demo)
# ============================================================================
variable "enable_redshift" {
  description = "Enable Redshift Serverless (expensive - only for demo). Set to false for low-cost Athena workflow."
  type        = bool
  default     = false
}

variable "enable_cloudwatch_alarms" {
  description = "Enable CloudWatch alarms for monitoring"
  type        = bool
  default     = false
}

variable "enable_kinesis" {
  description = "Enable Kinesis Data Stream (set false if using direct S3 ingestion for testing)"
  type        = bool
  default     = true
}

variable "enable_lambda" {
  description = "Enable Lambda fraud scorer (set false if testing without real-time processing)"
  type        = bool
  default     = true
}

# ============================================================================
# Kinesis Configuration
# ============================================================================
variable "kinesis_shard_count" {
  description = "Number of shards for Kinesis stream"
  type        = number
  default     = 1
}

variable "kinesis_retention_hours" {
  description = "Data retention period in hours for Kinesis stream"
  type        = number
  default     = 24
}

variable "lambda_memory_size" {
  description = "Memory size for Lambda function in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Timeout for Lambda function in seconds"
  type        = number
  default     = 300
}

variable "lambda_batch_size" {
  description = "Maximum number of records in each Kinesis batch"
  type        = number
  default     = 100
}

# ============================================================================
# Kinesis Firehose Configuration
# ============================================================================
variable "firehose_buffer_size_mb" {
  description = "Buffer size in MB for Firehose (triggers flush when reached)"
  type        = number
  default     = 64
  validation {
    condition     = var.firehose_buffer_size_mb >= 1 && var.firehose_buffer_size_mb <= 128  
    error_message = "Firehose buffer size must be between 1 and 128 MB when dynamic partitioning is enabled."
  }
}

variable "firehose_buffer_interval_sec" {
  description = "Buffer interval in seconds for Firehose (triggers flush when reached)"
  type        = number
  default     = 180
  validation {
    condition     = var.firehose_buffer_interval_sec >= 60 && var.firehose_buffer_interval_sec <= 900
    error_message = "Firehose buffer interval must be between 60 and 900 seconds, as required by AWS Kinesis Firehose service limits."
  }
}

variable "redshift_base_capacity" {
  description = "Base capacity for Redshift Serverless in RPUs (minimum 4, recommended 4-8 for dev demos)"
  type        = number
  default     = 4

  validation {
    condition     = var.redshift_base_capacity >= 4
    error_message = "Redshift Serverless requires minimum base_capacity of 4 RPUs."
  }
}

variable "redshift_rpu_hour_limit" {
  description = "Monthly RPU-hour usage limit for Redshift (guardrail to prevent runaway costs). Default 50 = ~$19/month"
  type        = number
  default     = 50
}

variable "redshift_admin_username" {
  description = "Admin username for Redshift"
  type        = string
  default     = "admin"
}

# ============================================================================
# S3 Lifecycle Configuration
# ============================================================================
variable "s3_raw_expiration_days" {
  description = "Number of days before raw data expires (keep low for portfolio/dev)"
  type        = number
  default     = 7
}

variable "s3_enriched_transition_days" {
  description = "Number of days before enriched data transitions to Glacier (keep low for portfolio/dev)"
  type        = number
  default     = 30
}

# ============================================================================
# Monitoring Configuration
# ============================================================================
variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days (keep low for dev to reduce costs)"
  type        = number
  default     = 3
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}
