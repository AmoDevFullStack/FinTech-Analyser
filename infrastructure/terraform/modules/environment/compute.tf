data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    compose_version = "v2.29.7"
    compose_sha256  = "383ce6698cd5d5bbf958d2c8489ed75094e34a77d340404d9f32c4ae9e12baf0"
    deploy_path     = local.deploy_path
  })

  disable_api_termination = var.deletion_protection

  # IMDSv2 only, one hop: containers cannot reach the instance's credentials.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # "standard": a CPU-bound runaway is throttled instead of billed. Switch to "unlimited" if
  # the CloudWatch CPUCreditBalance metric ever sits at zero.
  credit_specification {
    cpu_credits = "standard"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  tags = { Name = "${local.name}-app" }

  lifecycle {
    # A newer AMI or edited bootstrap script must not silently replace a running host.
    # Rebuild deliberately: terraform apply -replace=module.environment.aws_instance.app
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id
  tags     = { Name = "${local.name}-app" }
}
