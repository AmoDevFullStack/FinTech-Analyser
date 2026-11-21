variable "aws_region" {
  type    = string
  default = "af-south-1"
}

variable "project" {
  type    = string
  default = "fintech-analyser"
}

variable "github_repository" {
  description = "owner/name, exactly as GitHub shows it. IAM compares the OIDC subject case-sensitively."
  type        = string
  default     = "AmoDevFullStack/FinTech-Analyser"
}

variable "budget_alert_email" {
  description = "Where AWS Budgets sends cost alerts. Set in terraform.tfvars (gitignored)."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Alert at 80% of this actual spend and at 100% forecast."
  type        = number
  default     = 150
}
