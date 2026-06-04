# -----------------------------------------------------------------------
# VPC Endpoints — NAT Gateway를 우회하여 AWS 서비스에 직접 접근
#
# ECS Fargate(프라이빗 서브넷)의 주요 AWS 트래픽을 NAT 없이 처리:
#   - ECR: Docker 이미지 pull (레이어당 수십 MB)
#   - S3: 업로드 파일 저장/조회, ECR 이미지 레이어 캐시
#   - Secrets Manager: 컨테이너 시작 시 환경변수 로드
#   - CloudWatch Logs: structlog JSON 로그 전송
#
# Gateway Endpoint(S3)는 무료. Interface Endpoint는 ~$0.013/hr × 4 = ~$38/월.
# ECR 이미지 레이어 전송비 절감으로 비용이 상쇄됩니다.
# -----------------------------------------------------------------------

# S3 Gateway Endpoint (무료)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = { Name = "${var.project_name}-vpce-s3" }
}

# ECR API — 이미지 메타데이터 조회
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-vpce-ecr-api" }
}

# ECR DKR — 이미지 레이어 전송
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-vpce-ecr-dkr" }
}

# Secrets Manager — ECS 태스크 시작 시 시크릿 로드
resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-vpce-secretsmanager" }
}

# CloudWatch Logs — structlog JSON 로그 직접 전송
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-vpce-logs" }
}
