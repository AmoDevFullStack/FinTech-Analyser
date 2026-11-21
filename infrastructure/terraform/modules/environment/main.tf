data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name       = "${var.project}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  partition  = data.aws_partition.current.partition
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)

  # SSM Parameter Store layout:
  #   /<project>/<env>/app/<NAME>      rendered into the host's .env at every deploy
  #   /<project>/<env>/deploy/config   JSON the deploy workflow reads to find everything
  parameter_root     = "/${var.project}/${var.environment}"
  app_parameter_path = "${local.parameter_root}/app"

  ecr_registry   = "${local.account_id}.dkr.ecr.${local.region}.amazonaws.com"
  image_registry = "${local.ecr_registry}/${var.ecr_repository_prefix}"
  deploy_path    = "/opt/${var.project}"
}
