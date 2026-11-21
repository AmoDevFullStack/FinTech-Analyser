output "public_ip" {
  description = "Point app_domain's A record here if Route 53 does not manage it."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "Shell access: aws ssm start-session --target <this>"
  value       = aws_instance.app.id
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "deploy_role_arn" {
  description = "Set as AWS_DEPLOY_ROLE_ARN in this GitHub environment"
  value       = aws_iam_role.deploy.arn
}

output "app_parameter_path" {
  value = local.app_parameter_path
}

output "app_url" {
  description = "Set as APP_URL in this GitHub environment"
  value       = var.app_domain != "" ? "https://${var.app_domain}" : "http://${aws_eip.app.public_ip}"
}
