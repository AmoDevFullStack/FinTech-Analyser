# Application configuration, rendered into the host's .env by remote-deploy.sh on every
# deploy. The parameter name after /app/ IS the environment variable name.
#
# Optional settings are not created here; add them by hand and the next deploy picks them up:
#   aws ssm put-parameter --type SecureString \
#     --name /fintech-analyser/<env>/app/OPENAI_API_KEY --value sk-...

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "jwt_secret_key" {
  length  = 64
  special = false
}

resource "aws_ssm_parameter" "secret_key" {
  name  = "${local.app_parameter_path}/SECRET_KEY"
  type  = "SecureString"
  value = random_password.secret_key.result
}

# Separate from SECRET_KEY, so rotating token signing does not log out every cookie session.
resource "aws_ssm_parameter" "jwt_secret_key" {
  name  = "${local.app_parameter_path}/JWT_SECRET_KEY"
  type  = "SecureString"
  value = random_password.jwt_secret_key.result
}

resource "aws_ssm_parameter" "database_url" {
  name  = "${local.app_parameter_path}/DATABASE_URL"
  type  = "SecureString"
  value = "postgresql+psycopg://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${aws_db_instance.main.db_name}?sslmode=require"
}

resource "aws_ssm_parameter" "app_domain" {
  count          = var.app_domain == "" ? 0 : 1
  name           = "${local.app_parameter_path}/APP_DOMAIN"
  type           = "String"
  insecure_value = var.app_domain
}

# Everything scripts/aws_deploy.py needs to find this environment, so GitHub only has to
# know the deploy role ARN and the region.
resource "aws_ssm_parameter" "deploy_config" {
  name = "${local.parameter_root}/deploy/config"
  type = "String"
  insecure_value = jsonencode({
    region                   = local.region
    instance_id              = aws_instance.app.id
    db_instance_id           = aws_db_instance.main.identifier
    release_bucket           = aws_s3_bucket.releases.bucket
    image_registry           = local.image_registry
    app_parameter_path       = local.app_parameter_path
    deploy_path              = local.deploy_path
    predeploy_snapshots_kept = var.predeploy_snapshots_kept
  })
}
