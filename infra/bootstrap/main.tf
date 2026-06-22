# -----------------------------------------------------------------------
# Bootstrap — 최초 1회만 로컬에서 수동 실행
#
# 생성 리소스:
#   - S3 버킷 (Terraform state 저장, 버전 관리 + 암호화)
#   - DynamoDB 테이블 (state 잠금)
#   - GitHub Actions OIDC Provider
#   - IAM Role (GitHub Actions → AWS 배포 권한)
#
# 사용법:
#   cd infra/bootstrap
#   cp terraform.tfvars.example terraform.tfvars  # github_org, github_repo 입력
#   terraform init && terraform apply
#   terraform output  # role ARN, bucket 이름 확인 후 GitHub Secrets에 등록
# -----------------------------------------------------------------------

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---- S3 (Terraform state) ----

resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project_name}-terraform-state"

  lifecycle {
    prevent_destroy = true
  }

  tags = { Name = "${var.project_name}-terraform-state" }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---- DynamoDB (state 잠금) ----

resource "aws_dynamodb_table" "tf_lock" {
  name         = "${var.project_name}-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = { Name = "${var.project_name}-terraform-lock" }
}

# ---- GitHub Actions OIDC Provider ----

data "aws_iam_openid_connect_provider" "github" {
  count = 0  # 이미 존재하면 1로 변경하고 아래 resource 블록 제거
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  # GitHub Actions OIDC 인증서 thumbprint (고정값)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# ---- IAM Role (GitHub Actions 배포용) ----

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "github_actions" {
  name = "${var.project_name}-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # main 브랜치 push/PR + son_branch(plan_only 검토용 workflow_dispatch)에서만 권한 부여.
          # 이 역할은 AdministratorAccess라 브랜치를 와일드카드(refs/heads/*)로 열면 어떤 브랜치든
          # 그 권한을 가져갈 수 있어 노출 범위가 커진다 — 그래서 지금 실제로 쓰는 브랜치만 명시.
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/son_branch",
          ]
        }
      }
    }]
  })

  tags = { Name = "${var.project_name}-github-actions-role" }
}

resource "aws_iam_role_policy_attachment" "github_actions_admin" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
