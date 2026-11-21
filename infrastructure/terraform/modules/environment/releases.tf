# Release files (docker-compose.prod.yml, remote-deploy.sh, Caddyfile) for each deploy are
# uploaded here by the workflow and fetched by the host. Nothing here is secret or needed
# for long: images live in ECR, data in RDS.

resource "aws_s3_bucket" "releases" {
  bucket        = "${local.name}-releases-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "releases" {
  bucket                  = aws_s3_bucket.releases.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "releases" {
  bucket = aws_s3_bucket.releases.id
  rule {
    id     = "expire-releases"
    status = "Enabled"
    filter {
      prefix = "releases/"
    }
    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_policy" "releases" {
  bucket = aws_s3_bucket.releases.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.releases.arn, "${aws_s3_bucket.releases.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.releases]
}
