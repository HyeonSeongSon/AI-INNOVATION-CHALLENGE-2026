# -----------------------------------------------------------------------
# [이슈 1] NAT Gateway — 프라이빗 서브넷의 아웃바운드 인터넷 연결
#
# ECS Fargate(프라이빗 서브넷)가 외부 API(OpenAI, Anthropic)를 호출하고
# 소스 업데이트를 받으려면 NAT Gateway가 필수입니다.
#
# 비용 (서울 리전 ap-northeast-2):
#   고정:  $0.059/hr × 730h = ~$43/월
#   전송:  $0.059/GB (ECR, S3, SecretsManager는 VPC Endpoint로 우회 — vpc_endpoints.tf 참고)
#   실제:  NAT 경유 트래픽이 외부 LLM API 호출에 한정되므로 전송비는 소액
#
# 단일 NAT GW를 사용합니다. HA가 필요하면 AZ별로 1개씩 추가하세요.
# -----------------------------------------------------------------------

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${var.project_name}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = { Name = "${var.project_name}-nat-gw" }

  depends_on = [aws_internet_gateway.main]
}

# 프라이빗 서브넷의 기본 경로를 NAT Gateway로 설정
resource "aws_route" "private_nat" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main.id
}
