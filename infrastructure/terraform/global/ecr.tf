# One repository per image, shared by every environment: staging and production run the
# same image digests, which is the whole point of promoting instead of rebuilding.

locals {
  images = toset(["backend", "frontend"])
}

resource "aws_ecr_repository" "image" {
  for_each = local.images
  name     = "${var.project}/${each.key}"

  # Mutable so `main` and release tags can be (re)pointed. Deploys never use a mutable tag:
  # they always reference the full commit SHA.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "image" {
  for_each   = aws_ecr_repository.image
  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        # Release images (vX.Y.Z) are what a production rollback needs: keep them. A rule
        # with higher priority protects its matches from every lower-priority rule.
        rulePriority = 1
        description  = "Keep release-tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 9999
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged layers after a week"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 3
        description  = "Keep the 60 most recent main builds"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 60
        }
        action = { type = "expire" }
      },
    ]
  })
}
