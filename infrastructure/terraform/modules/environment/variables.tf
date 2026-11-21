variable "project" {
  type    = string
  default = "fintech-analyser"
}

variable "environment" {
  description = "staging or production. Also the GitHub environment name the deploy role trusts."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.environment))
    error_message = "Lowercase letters, digits and hyphens."
  }
}

variable "github_repository" {
  description = "owner/name, exactly as GitHub shows it (the OIDC subject is case-sensitive)."
  type        = string
  default     = "AmoDevFullStack/FinTech-Analyser"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

# --- Application host ---------------------------------------------------------------------

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "root_volume_gb" {
  type    = number
  default = 30
}

# --- Database -----------------------------------------------------------------------------

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_max_allocated_storage_gb" {
  description = "Storage autoscaling ceiling. RDS grows the volume on its own up to this."
  type        = number
  default     = 100
}

variable "db_multi_az" {
  description = "Standby in a second AZ with automatic failover. Roughly doubles the database cost."
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = "Automated backups and point-in-time restore window (1-35)."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Protects the database and instance from deletion, and keeps a final snapshot."
  type        = bool
  default     = true
}

# --- Delivery -----------------------------------------------------------------------------

variable "app_domain" {
  description = "Public host name, e.g. app.example.com. Caddy gets its TLS certificate for it. Empty = HTTP only (logins will not work: session cookies are Secure)."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Optional hosted zone for app_domain. Empty = point your DNS at the elastic IP yourself."
  type        = string
  default     = ""
}

variable "predeploy_snapshots_kept" {
  description = "Manual RDS snapshots taken before each deploy, newest first, that are kept."
  type        = number
  default     = 10
}

variable "ecr_repository_prefix" {
  description = "ECR repositories created by the global stack: <prefix>/backend, <prefix>/frontend."
  type        = string
  default     = "fintech-analyser"
}
