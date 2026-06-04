output "github_actions_role_arn" {
  description = "GitHub Secrets → AWS_ROLE_ARN 에 등록"
  value       = aws_iam_role.github_actions.arn
}

output "terraform_state_bucket" {
  description = "Terraform state S3 버킷명"
  value       = aws_s3_bucket.tf_state.bucket
}

output "terraform_lock_table" {
  description = "Terraform state 잠금 DynamoDB 테이블명"
  value       = aws_dynamodb_table.tf_lock.name
}

output "ecr_registry" {
  description = "ECR 레지스트리 URI — GitHub Actions TF_VAR_ecr_registry 또는 deploy.yml의 account ID 조회로 자동 주입"
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "ecr_repository_urls" {
  description = "서비스별 ECR 레포 URI 목록"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}
