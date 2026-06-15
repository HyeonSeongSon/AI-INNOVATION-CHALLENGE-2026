# -----------------------------------------------------------------------
# Admin Seed Secrets — 최초 배포 시 admin 계정 생성용
#
# 사용법:
#   1. terraform.tfvars에 admin_seed_email, admin_seed_password 입력
#   2. terraform apply → Secrets Manager 시크릿 생성 + ECS 재시작
#   3. CloudWatch Logs에서 "admin_seeded" 확인 후 로그인 검증
#   4. terraform.tfvars에서 두 값을 ""로 교체 → terraform apply
#      → count=0으로 시크릿 즉시 삭제 (recovery_window_in_days=0)
# -----------------------------------------------------------------------

locals {
  admin_seed_enabled = var.admin_seed_email != ""
}

resource "aws_secretsmanager_secret" "admin_seed_email" {
  count                   = local.admin_seed_enabled ? 1 : 0
  name                    = "${var.project_name}/admin-seed-email"
  description             = "Admin seed email - delete after seeding"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin_seed_email" {
  count         = local.admin_seed_enabled ? 1 : 0
  secret_id     = aws_secretsmanager_secret.admin_seed_email[0].id
  secret_string = var.admin_seed_email
}

resource "aws_secretsmanager_secret" "admin_seed_password" {
  count                   = local.admin_seed_enabled ? 1 : 0
  name                    = "${var.project_name}/admin-seed-password"
  description             = "Admin seed password - delete after seeding"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin_seed_password" {
  count         = local.admin_seed_enabled ? 1 : 0
  secret_id     = aws_secretsmanager_secret.admin_seed_password[0].id
  secret_string = var.admin_seed_password
}

# -----------------------------------------------------------------------
# DB API Secrets — db-api EC2 서비스용 (INTERNAL_TOKEN)
# EC2 IAM 역할이 secretsmanager:GetSecretValue ${project_name}/* 권한 보유
# -----------------------------------------------------------------------

resource "aws_secretsmanager_secret" "db_api_internal_token" {
  name                    = "${var.project_name}/db-api-internal-token"
  description             = "INTERNAL_TOKEN for db-api service on EC2"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_api_internal_token" {
  secret_id     = aws_secretsmanager_secret.db_api_internal_token.id
  secret_string = var.internal_token
}

# -----------------------------------------------------------------------
# ECS Sensitive Env Secrets — task definition 평문 노출 제거용
#
# 기존엔 POSTGRES_URL/PASSWORD/JWT/토큰/API키가 task def environment에 평문으로
# 들어가 ecs:DescribeTaskDefinition으로 조회됐다. Secrets Manager로 옮겨
# ECS `secrets` 블록(valueFrom)으로 주입한다 — admin-seed와 동일 패턴.
# ECS execution role이 secretsmanager:GetSecretValue ${project_name}/* 권한 보유.
# -----------------------------------------------------------------------

resource "aws_secretsmanager_secret" "postgres_url" {
  name                    = "${var.project_name}/postgres-url"
  description             = "POSTGRES_URL (contains password) for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "postgres_url" {
  secret_id     = aws_secretsmanager_secret.postgres_url.id
  secret_string = local.postgres_url
}

resource "aws_secretsmanager_secret" "postgres_password" {
  name                    = "${var.project_name}/postgres-password"
  description             = "POSTGRES_PASSWORD for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "postgres_password" {
  secret_id     = aws_secretsmanager_secret.postgres_password.id
  secret_string = var.postgres_password
}

resource "aws_secretsmanager_secret" "internal_token" {
  name                    = "${var.project_name}/internal-token"
  description             = "INTERNAL_TOKEN for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "internal_token" {
  secret_id     = aws_secretsmanager_secret.internal_token.id
  secret_string = var.internal_token
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "${var.project_name}/jwt-secret"
  description             = "JWT_SECRET for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = var.jwt_secret
}

# API 키는 사용하는 모델에 따라 한쪽만 설정됨(gpt면 openai, claude면 anthropic).
# 빈 값은 Secrets Manager가 거부하므로 값이 있을 때만 시크릿 생성.
resource "aws_secretsmanager_secret" "openai_api_key" {
  count                   = var.openai_api_key != "" ? 1 : 0
  name                    = "${var.project_name}/openai-api-key"
  description             = "OPENAI_API_KEY for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  count         = var.openai_api_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.openai_api_key[0].id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  count                   = var.anthropic_api_key != "" ? 1 : 0
  name                    = "${var.project_name}/anthropic-api-key"
  description             = "ANTHROPIC_API_KEY for ECS tasks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "anthropic_api_key" {
  count         = var.anthropic_api_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.anthropic_api_key[0].id
  secret_string = var.anthropic_api_key
}
