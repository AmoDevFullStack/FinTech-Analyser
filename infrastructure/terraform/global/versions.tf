terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # Partial configuration: bucket and region come from ../backend.hcl.
  #   terraform init -backend-config=../backend.hcl
  backend "s3" {
    key = "global/terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Stack     = "global"
    }
  }
}
