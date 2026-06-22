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

output "opensearch_api_ec2_private_ip" {
  description = "OpenSearch API EC2 프라이빗 IP (임베딩 추론, OpenSearch 노드와 분리)"
  value       = aws_instance.opensearch_api.private_ip
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

output "opensearch_api_ec2_instance_id" {
  description = <<-EOT
    OpenSearch API 단일 EC2 인스턴스 ID (SSM Run Command 타겟) — ASG 전환 롤아웃이 끝나고
    이 단일 인스턴스 리소스를 제거하면 이 output도 같이 삭제한다. 그 전까지는 빌더 인스턴스의
    "최초 1회" 소스로도 쓰인다(opensearch_api_asg.tf 주석 참고).
  EOT
  value       = aws_instance.opensearch_api.id
}

output "opensearch_api_launch_template_id" {
  description = "OpenSearch API ASG launch template ID — CI가 create-launch-template-version 호출 시 사용"
  value       = aws_launch_template.opensearch_api.id
}

output "opensearch_api_asg_name" {
  description = "OpenSearch API Auto Scaling Group 이름 — CI가 start-instance-refresh 호출 시 사용. 단일 인스턴스 ID와 달리 인스턴스 목록은 그때그때 aws autoscaling describe-auto-scaling-groups로 조회해야 한다."
  value       = aws_autoscaling_group.opensearch_api.name
}

output "opensearch_api_nlb_dns_name" {
  description = "OpenSearch API 내부 NLB DNS 이름"
  value       = aws_lb.opensearch_api.dns_name
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
