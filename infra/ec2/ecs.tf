# -----------------------------------------------------------------------
# ECS Fargate — 5개 FastAPI 서비스
#
# 서비스 간 통신:
#   - fastapi-backend(8005): ALB → ECS (외부 노출)
#   - crm-service(8006): ECS Service Discovery (crm-service.crm.local:8006)
#   - recommend-agent(8001): ECS Service Discovery
#   - generate-agent(8002): ECS Service Discovery
#   - data-registration-agent(8003): ECS Service Discovery
#
# settings.py의 URL 환경변수를 Cloud Map DNS로 오버라이드합니다:
#   RECOMMEND_AGENT_URL=http://recommend-agent.crm.local:8001
#   GENERATE_MESSAGE_AGENT_URL=http://generate-agent.crm.local:8002
#   DATA_REGISTRATION_AGENT_URL=http://data-registration-agent.crm.local:8003
#   CRM_SERVICE_URL=http://crm-service.crm.local:8006
# -----------------------------------------------------------------------

locals {
  # EC2 프라이빗 IP 기반 URL — ECS 태스크 환경변수에 주입
  db_api_url         = "http://${aws_instance.db.private_ip}:8020"
  opensearch_api_url = "http://${aws_instance.opensearch_api.private_ip}:8010"
  postgres_url       = "postgresql://${var.postgres_user}:${var.postgres_password}@${aws_instance.db.private_ip}:5432/ai_innovation_db"
}

variable "postgres_user" {
  description = "PostgreSQL 사용자명"
  type        = string
  default     = "postgres"
}

# ---- ECS Cluster ----

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ---- CloudWatch Log Group ----

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 30
}

# ---- Service Discovery (AWS Cloud Map) ----

resource "aws_service_discovery_private_dns_namespace" "crm" {
  name        = "crm.local"
  description = "ai-innovation 내부 서비스 DNS"
  vpc         = aws_vpc.main.id
}

# ---- IAM Task Role (런타임 — 앱이 AWS API를 직접 호출할 때 사용) ----

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# Admin seed 시크릿 삭제 권한 — 앱이 시딩 완료 후 스스로 삭제
resource "aws_iam_role_policy" "ecs_task_seed_delete" {
  name = "${var.project_name}-ecs-task-seed-delete"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:DeleteSecret"]
      Resource = [
        "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/admin-seed-email*",
        "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/admin-seed-password*",
      ]
    }]
  })
}

# ---- IAM Task Execution Role ----

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Secrets Manager 접근 권한 (ECR Endpoint를 통해 시크릿 로드)
resource "aws_iam_role_policy" "ecs_secrets" {
  name = "${var.project_name}-ecs-secrets-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*"
    }]
  })
}

# ---- 공통 환경변수 (모든 ECS 태스크 공유) ----

locals {
  # 비민감 환경변수만 평문 environment로 주입.
  # 민감 값(POSTGRES_URL/PASSWORD/INTERNAL_TOKEN/JWT_SECRET/API키)은 common_secrets로 분리 —
  # task def JSON 평문 노출(ecs:DescribeTaskDefinition) 제거.
  common_env = [
    { name = "DATABASE_API_URL", value = local.db_api_url },
    { name = "OPENSEARCH_API_URL", value = local.opensearch_api_url },
    { name = "POSTGRES_HOST", value = aws_instance.db.private_ip },
    { name = "CHATGPT_MODEL_NAME", value = var.chatgpt_model_name },
    { name = "PARSER_MODEL_NAME", value = var.parser_model_name },
    { name = "ENVIRONMENT", value = var.environment },
    { name = "LOG_LEVEL", value = "INFO" },
    # ALLOWED_ORIGINS: 모든 서비스에 주입 — Settings 프로덕션 검증이 localhost를 거부하므로
    # CRM·recommend·generate·data-registration 같은 내부 서비스도 이 값이 필요함
    { name = "ALLOWED_ORIGINS", value = jsonencode(split(",", var.allowed_origins)) },
    # TRUSTED_PROXY_IPS: ALB는 VPC 프라이빗 서브넷에서 ECS로 전달
    # ALB가 신뢰 프록시이므로 프라이빗 서브넷 CIDR을 허용
    { name = "TRUSTED_PROXY_IPS", value = jsonencode(var.private_subnet_cidrs) },
    { name = "TRUSTED_PROXY_COUNT", value = "1" },
  ]

  # 민감 환경변수 — Secrets Manager에서 valueFrom으로 주입 (모든 서비스 공통)
  # API 키는 설정된 것만 주입 (빈 키는 시크릿 미생성 → 여기서도 제외)
  common_secrets = concat(
    [
      { name = "POSTGRES_URL", valueFrom = aws_secretsmanager_secret.postgres_url.arn },
      { name = "POSTGRES_PASSWORD", valueFrom = aws_secretsmanager_secret.postgres_password.arn },
      { name = "INTERNAL_TOKEN", valueFrom = aws_secretsmanager_secret.internal_token.arn },
      { name = "JWT_SECRET", valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
    ],
    var.openai_api_key != "" ? [
      { name = "OPENAI_API_KEY", valueFrom = aws_secretsmanager_secret.openai_api_key[0].arn },
    ] : [],
    var.anthropic_api_key != "" ? [
      { name = "ANTHROPIC_API_KEY", valueFrom = aws_secretsmanager_secret.anthropic_api_key[0].arn },
    ] : [],
  )

  # A2A 서비스 URL — Cloud Map DNS 이름
  a2a_env = [
    { name = "RECOMMEND_AGENT_URL", value = "http://recommend-agent.crm.local:8001" },
    { name = "GENERATE_MESSAGE_AGENT_URL", value = "http://generate-agent.crm.local:8002" },
    { name = "DATA_REGISTRATION_AGENT_URL", value = "http://data-registration-agent.crm.local:8003" },
    { name = "CRM_SERVICE_URL", value = "http://crm-service.crm.local:8006" },
  ]

  # 컨테이너 healthCheck — /health 200 확인 (python-slim 이미지, 의존성 없는 urllib 사용)
  # 헬퍼: 포트를 받아 healthCheck 맵 생성
  healthcheck = {
    for port in [8005, 8006, 8001, 8002, 8003] : port => {
      command     = ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:${port}/health').status==200 else 1)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }
}

# ---- Task Definitions ----

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([{
    name         = "fastapi-backend"
    image        = "${var.ecr_registry}/${var.project_name}-backend:${var.ecr_image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8005, protocol = "tcp" }]
    environment  = concat(local.common_env, local.a2a_env)
    healthCheck  = local.healthcheck[8005]
    # Secrets Manager — ECS가 태스크 시작 시 주입, 태스크 정의 JSON에 값 미노출
    secrets = concat(local.common_secrets, local.admin_seed_enabled ? [
      {
        name      = "ADMIN_SEED_EMAIL"
        valueFrom = aws_secretsmanager_secret.admin_seed_email[0].arn
      },
      {
        name      = "ADMIN_SEED_PASSWORD"
        valueFrom = aws_secretsmanager_secret.admin_seed_password[0].arn
      }
    ] : [])
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "backend"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "crm" {
  family                   = "${var.project_name}-crm"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name         = "crm-service"
    image        = "${var.ecr_registry}/${var.project_name}-crm:${var.ecr_image_tag}"
    essential    = true
    command      = ["uvicorn", "servers.crm_server:app", "--host", "0.0.0.0", "--port", "8006"]
    portMappings = [{ containerPort = 8006, protocol = "tcp" }]
    environment  = concat(local.common_env, local.a2a_env)
    secrets      = local.common_secrets
    healthCheck  = local.healthcheck[8006]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "crm"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "recommend" {
  family                   = "${var.project_name}-recommend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name         = "recommend-agent"
    image        = "${var.ecr_registry}/${var.project_name}-recommend:${var.ecr_image_tag}"
    essential    = true
    command      = ["uvicorn", "servers.recommend_server:app", "--host", "0.0.0.0", "--port", "8001"]
    portMappings = [{ containerPort = 8001, protocol = "tcp" }]
    environment  = local.common_env
    secrets      = local.common_secrets
    healthCheck  = local.healthcheck[8001]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "recommend"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "generate" {
  family                   = "${var.project_name}-generate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name         = "generate-agent"
    image        = "${var.ecr_registry}/${var.project_name}-generate:${var.ecr_image_tag}"
    essential    = true
    command      = ["uvicorn", "servers.generate_server:app", "--host", "0.0.0.0", "--port", "8002"]
    portMappings = [{ containerPort = 8002, protocol = "tcp" }]
    environment  = local.common_env
    secrets      = local.common_secrets
    healthCheck  = local.healthcheck[8002]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "generate"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "data_registration" {
  family                   = "${var.project_name}-data-registration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name         = "data-registration-agent"
    image        = "${var.ecr_registry}/${var.project_name}-data-registration:${var.ecr_image_tag}"
    essential    = true
    command      = ["uvicorn", "servers.data_registration_server:app", "--host", "0.0.0.0", "--port", "8003"]
    portMappings = [{ containerPort = 8003, protocol = "tcp" }]
    environment  = local.common_env
    secrets      = local.common_secrets
    healthCheck  = local.healthcheck[8003]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "data-registration"
      }
    }
  }])
}

# ---- ECS Services ----

# fastapi-backend — ALB Target Group에 연결
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.ecs_service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "fastapi-backend"
    container_port   = 8005
  }

  depends_on = [aws_lb_listener.http]
}

# crm-service — Service Discovery 등록
resource "aws_service_discovery_service" "crm" {
  name = "crm-service"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.crm.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_service" "crm" {
  name            = "${var.project_name}-crm"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.crm.arn
  desired_count   = var.ecs_service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.crm.arn
  }
}

# recommend-agent
resource "aws_service_discovery_service" "recommend" {
  name = "recommend-agent"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.crm.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_service" "recommend" {
  name            = "${var.project_name}-recommend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.recommend.arn
  desired_count   = var.ecs_service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.recommend.arn
  }
}

# generate-agent
resource "aws_service_discovery_service" "generate" {
  name = "generate-agent"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.crm.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_service" "generate" {
  name            = "${var.project_name}-generate"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.generate.arn
  desired_count   = var.ecs_service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.generate.arn
  }
}

# data-registration-agent
resource "aws_service_discovery_service" "data_registration" {
  name = "data-registration-agent"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.crm.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_service" "data_registration" {
  name            = "${var.project_name}-data-registration"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.data_registration.arn
  desired_count   = var.ecs_service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.data_registration.arn
  }
}
