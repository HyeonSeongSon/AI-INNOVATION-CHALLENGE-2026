terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # S3 백엔드 — 팀 협업 시 활성화
  # backend "s3" {
  #   bucket = "ai-innovation-tfstate"
  #   key    = "ec2/terraform.tfstate"
  #   region = "ap-northeast-2"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ai-innovation-challenge"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
