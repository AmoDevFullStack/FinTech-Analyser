output "ecr_registry" {
  description = "IMAGE_REGISTRY prefix; images are <this>/backend and <this>/frontend"
  value       = "${split("/", aws_ecr_repository.image["backend"].repository_url)[0]}/${var.project}"
}

output "github_build_role_arn" {
  description = "Set as the repository variable AWS_BUILD_ROLE_ARN"
  value       = aws_iam_role.build.arn
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}
