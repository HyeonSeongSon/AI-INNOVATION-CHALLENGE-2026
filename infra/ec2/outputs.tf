output "alb_dns_name" {
  description = "ALB DNS 이름 (Route 53 CNAME 또는 직접 접속)"
  value       = aws_lb.main.dns_name
}

output "db_ec2_private_ip" {
  description = "PostgreSQL EC2 프라이빗 IP"
  value       = aws_instance.db.private_ip
}

output "opensearch_ec2_private_ip" {
  description = "OpenSearch EC2 프라이빗 IP"
  value       = aws_instance.opensearch.private_ip
}

output "ecs_cluster_name" {
  description = "ECS 클러스터 이름"
  value       = aws_ecs_cluster.main.name
}

output "service_discovery_namespace" {
  description = "Cloud Map 네임스페이스 (서비스 간 DNS 도메인)"
  value       = aws_service_discovery_private_dns_namespace.crm.name
}

output "cloudwatch_log_group" {
  description = "ECS 서비스 로그 그룹"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "nat_gateway_eip" {
  description = "NAT Gateway 퍼블릭 IP (아웃바운드 화이트리스트용)"
  value       = aws_eip.nat.public_ip
}

output "db_ec2_instance_id" {
  description = "PostgreSQL EC2 인스턴스 ID (SSM Run Command 타겟)"
  value       = aws_instance.db.id
}

output "opensearch_ec2_instance_id" {
  description = "OpenSearch EC2 인스턴스 ID (SSM Run Command 타겟)"
  value       = aws_instance.opensearch.id
}

output "deploy_s3_bucket" {
  description = "앱 코드 아카이브 S3 버킷 이름"
  value       = aws_s3_bucket.deploy.bucket
}

output "cloudfront_domain_name" {
  description = "CloudFront 배포 도메인 (프론트엔드 접속 URL)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront 배포 ID (캐시 무효화용)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_s3_bucket" {
  description = "프론트엔드 정적 파일 S3 버킷"
  value       = aws_s3_bucket.frontend.bucket
}
