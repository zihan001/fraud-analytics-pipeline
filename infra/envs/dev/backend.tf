terraform {
  backend "s3" {
    bucket         = "fraud-analytics-tfstate-735702560596"
    key            = "dev/terraform.tfstate"
    region         = "ca-central-1"
    dynamodb_table = "fraud-analytics-terraform-locks"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:ca-central-1:735702560596:key/12794834-c2b3-41e5-ad8f-145d51f7cbbd"
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
