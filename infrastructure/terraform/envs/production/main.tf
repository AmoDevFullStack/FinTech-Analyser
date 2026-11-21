terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # terraform init -backend-config=../../backend.hcl
  backend "s3" {
    key = "envs/production/terraform.tfstate"
  }
}

variable "aws_region" {
  type    = string
  default = "af-south-1"
}

variable "app_domain" {
  description = "e.g. app.example.com. Set in terraform.tfvars."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  type    = string
  default = ""
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "fintech-analyser"
      Environment = "production"
      ManagedBy   = "terraform"
    }
  }
}

module "environment" {
  source = "../../modules/environment"

  environment     = "production"
  app_domain      = var.app_domain
  route53_zone_id = var.route53_zone_id

  # Real financial data: deletion protection, two weeks of point-in-time restore, and a
  # final snapshot if the database is ever deleted. Set db_multi_az = true when the cost of
  # an hour of downtime exceeds the cost of a standby (it roughly doubles the RDS line).
  instance_type            = "t3.small"
  db_instance_class        = "db.t3.small"
  db_multi_az              = false
  db_backup_retention_days = 14
  deletion_protection      = true
  vpc_cidr                 = "10.30.0.0/16"
}

output "public_ip" {
  value = module.environment.public_ip
}

output "instance_id" {
  value = module.environment.instance_id
}

output "deploy_role_arn" {
  value = module.environment.deploy_role_arn
}

output "app_url" {
  value = module.environment.app_url
}

output "db_endpoint" {
  value = module.environment.db_endpoint
}
