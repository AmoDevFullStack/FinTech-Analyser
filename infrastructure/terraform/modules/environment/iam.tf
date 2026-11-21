# ---------------------------------------------------------------------------------------
# The app host's role: SSM agent, ECR pulls, its own app parameters and release files.
# ---------------------------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "app_ecr" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

data "aws_iam_policy_document" "app" {
  statement {
    sid     = "ReadOwnAppParameters"
    actions = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
    resources = [
      "arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter${local.app_parameter_path}",
      "arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter${local.app_parameter_path}/*",
    ]
  }
  statement {
    sid       = "FetchReleaseFiles"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.releases.arn}/releases/*"]
  }
  statement {
    sid       = "ListReleaseFiles"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.releases.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["releases/*"]
    }
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "app-runtime"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}

# ---------------------------------------------------------------------------------------
# The deploy role, assumed by GitHub Actions from jobs running in the GitHub environment of
# the same name. Production's required reviewers therefore gate its AWS credentials too.
# ---------------------------------------------------------------------------------------

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${local.name}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.deploy_trust.json
  max_session_duration = 3600
}

locals {
  snapshot_arn_pattern = "arn:${local.partition}:rds:${local.region}:${local.account_id}:snapshot:predeploy-${var.environment}-*"
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "ReadDeployConfig"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.deploy_config.arn]
  }
  statement {
    sid       = "UploadReleaseFiles"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.releases.arn}/releases/*"]
  }
  statement {
    sid     = "RunDeployOnTheHost"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.app.arn,
      "arn:${local.partition}:ssm:${local.region}::document/AWS-RunShellScript",
    ]
  }
  statement {
    sid       = "FollowDeployOutput"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
  statement {
    sid       = "WaitForDatabase"
    actions   = ["rds:DescribeDBInstances"]
    resources = [aws_db_instance.main.arn]
  }
  statement {
    sid       = "PreDeploySnapshots"
    actions   = ["rds:CreateDBSnapshot", "rds:AddTagsToResource"]
    resources = [aws_db_instance.main.arn, local.snapshot_arn_pattern]
  }
  statement {
    # Read-only metadata; list calls are not reliably resource-scoped, so "*".
    sid       = "ListSnapshots"
    actions   = ["rds:DescribeDBSnapshots"]
    resources = ["*"]
  }
  statement {
    # Only pre-deploy snapshots: automated backups and the final snapshot are out of reach.
    sid       = "PruneOldPreDeploySnapshots"
    actions   = ["rds:DeleteDBSnapshot"]
    resources = [local.snapshot_arn_pattern]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
