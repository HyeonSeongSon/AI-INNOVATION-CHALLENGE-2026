# -----------------------------------------------------------------------
# ECR 레포지토리 — bootstrap 계층 (CI/CD 전제 리소스)
#
# build-and-push GitHub Actions job이 이미지를 push하려면 ECR 레포가 먼저
# 존재해야 한다. ECR은 terraform job(이후 단계)이 만드는 운영 인프라가 아니라
# CI/CD 파이프라인 자체의 전제 리소스이므로 bootstrap에 위치한다.
# -----------------------------------------------------------------------

locals {
  services = ["backend", "crm", "recommend", "generate", "data-registration"]
}

resource "aws_ecr_repository" "services" {
  for_each             = toset(local.services)
  name                 = "${var.project_name}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${var.project_name}-${each.key}" }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "최근 10개 이미지만 보관"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
