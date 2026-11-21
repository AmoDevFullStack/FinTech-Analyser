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
    key = "envs/staging/terraform.tfstate"
  }
}

variable "aws_region" {
  type    = string
  default = "af-south-1"
}

variable "app_domain" {
  description = "e.g. staging.example.com. Set in terraform.tfvars."
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
      Environment = "staging"
      ManagedBy   = "terraform"
    }
  }
}

module "environment" {
  source = "../../modules/environment"

  environment     = "staging"
  app_domain      = var.app_domain
  route53_zone_id = var.route53_zone_id

  # Small and disposable: staging exists to rehearse deploys, not to hold real data.
  instance_type            = "t3.small"
  db_instance_class        = "db.t3.micro"
  db_multi_az              = false
  db_backup_retention_days = 3
  deletion_protection      = false
  vpc_cidr                 = "10.20.0.0/16"
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
