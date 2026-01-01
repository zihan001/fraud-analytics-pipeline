terraform {
  backend "s3" {
    bucket         = "fraud-analytics-terraform-state-735702560596"
    key            = "dev/terraform.tfstate"
    region         = "ca-west-1"
    dynamodb_table = "fraud-analytics-terraform-locks"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:ca-west-1:735702560596:key/80168d5c-ca02-4cc8-a234-283cb6f6245e"
  }

  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
