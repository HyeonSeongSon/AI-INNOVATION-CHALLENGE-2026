# -----------------------------------------------------------------------
# Security Groups
#
# 트래픽 흐름:
#   인터넷 → ALB(sg_alb) → ECS tasks(sg_ecs_tasks)
#   ECS tasks → DB EC2(sg_db_ec2)         [포트 5432, 8020]
#   ECS tasks → OpenSearch EC2(sg_opensearch_ec2) [포트 8010, 9200]
#   ECS/EC2  → VPC Endpoints(sg_vpc_endpoints)   [포트 443]
# -----------------------------------------------------------------------

# ---- ALB ----

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-sg-alb"
  description = "ALB: 인터넷 트래픽 수신"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg-alb" }
}

# ---- ECS Tasks ----

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-sg-ecs-tasks"
  description = "ECS Fargate: ALB에서만 8005 수신, 내부 서비스 간 통신"
  vpc_id      = aws_vpc.main.id

  # API Gateway(8005) — ALB에서만 수신
  ingress {
    description     = "API Gateway from ALB"
    from_port       = 8005
    to_port         = 8005
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # 내부 A2A 통신(8001–8006) — 동일 SG 내 ECS 태스크 간
  ingress {
    description = "Internal A2A (8001-8006)"
    from_port   = 8001
    to_port     = 8006
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg-ecs-tasks" }
}

# ---- DB EC2 ----

resource "aws_security_group" "db_ec2" {
  name        = "${var.project_name}-sg-db-ec2"
  description = "DB EC2: ECS tasks에서만 PostgreSQL/DB API 수신"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg-db-ec2" }
}

# -----------------------------------------------------------------------
# [이슈 6] LangGraph checkpointer — ECS tasks → PostgreSQL(5432) 인바운드
#
# crm-service ECS 태스크가 LangGraph PostgreSQL checkpointer를 통해
# DB EC2의 5432 포트에 직접 연결합니다.
# 이 규칙 없이 배포하면 checkpointer 초기화 시 연결 불가로 서비스가 시작되지 않습니다.
# -----------------------------------------------------------------------
resource "aws_security_group_rule" "ecs_to_postgres" {
  type                     = "ingress"
  description              = "[이슈 6] LangGraph checkpointer — ECS to PostgreSQL"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = aws_security_group.db_ec2.id
}

# Database API(8020) — ECS tasks에서 HTTP 호출
resource "aws_security_group_rule" "ecs_to_db_api" {
  type                     = "ingress"
  description              = "Database API server — ECS to DB API"
  from_port                = 8020
  to_port                  = 8020
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = aws_security_group.db_ec2.id
}

# ---- OpenSearch EC2 ----

resource "aws_security_group" "opensearch_ec2" {
  name        = "${var.project_name}-sg-opensearch-ec2"
  description = "OpenSearch EC2: ECS tasks에서만 OpenSearch API/native 수신"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg-opensearch-ec2" }
}

# OpenSearch API(8010) — ECS tasks에서 HTTP 호출
resource "aws_security_group_rule" "ecs_to_opensearch_api" {
  type                     = "ingress"
  description              = "OpenSearch API server — ECS to OpenSearch API"
  from_port                = 8010
  to_port                  = 8010
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = aws_security_group.opensearch_ec2.id
}

# OpenSearch native REST(9200) — ECS tasks에서 직접 호출 시
resource "aws_security_group_rule" "ecs_to_opensearch_native" {
  type                     = "ingress"
  description              = "OpenSearch native REST — ECS to OpenSearch 9200"
  from_port                = 9200
  to_port                  = 9200
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = aws_security_group.opensearch_ec2.id
}

# ---- VPC Interface Endpoints ----

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.project_name}-sg-vpc-endpoints"
  description = "VPC Interface Endpoints: VPC 내부 HTTPS 트래픽만 허용"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg-vpc-endpoints" }
}
