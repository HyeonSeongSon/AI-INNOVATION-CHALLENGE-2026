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
  description             = "Admin seed 이메일 — 시드 완료 후 삭제"
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
  description             = "Admin seed 비밀번호 — 시드 완료 후 삭제"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin_seed_password" {
  count         = local.admin_seed_enabled ? 1 : 0
  secret_id     = aws_secretsmanager_secret.admin_seed_password[0].id
  secret_string = var.admin_seed_password
}
