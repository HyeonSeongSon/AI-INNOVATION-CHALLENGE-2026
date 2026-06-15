# -----------------------------------------------------------------------
# [이슈 2] ALB — SSE 스트리밍 단절 방지
#
# 문제: ALB 기본 idle_timeout = 60s
# LangGraph 에이전트 체인(supervisor → recommend → generate)이 LLM을
# 연속 호출하면 총 소요 시간이 60s를 초과할 수 있습니다.
# settings.py의 graph_execution_timeout = 300s에 맞춰 300으로 설정합니다.
# -----------------------------------------------------------------------

resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # SSE 스트리밍 대응 — graph_execution_timeout(300s)에 맞춤
  idle_timeout = 300

  tags = { Name = "${var.project_name}-alb" }
}

# ---- HTTPS Listener (ACM 인증서가 있을 때만 생성) ----

resource "aws_lb_listener" "https" {
  count             = var.alb_ssl_certificate_arn != "" ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_ssl_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ---- HTTP Listener ----
# 인증서 없음(기본): 직접 포워드
# 인증서 있음: HTTPS 리다이렉트 리스너로 교체 (count = 1로 변경)

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# HTTPS 도입 후 HTTP → HTTPS 리다이렉트가 필요하면:
# 1. aws_lb_listener.http의 default_action을 redirect로 변경
# 2. alb_ssl_certificate_arn 변수에 ACM ARN 입력
# 3. terraform apply 실행

# ---- Target Group — fastapi-backend(8005)만 외부 노출 ----
# 나머지 서비스(8001, 8002, 8003, 8006)는 ECS Service Discovery(Cloud Map)로
# VPC 내부에서만 접근합니다.

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-tg-backend"
  port        = 8005
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Fargate는 IP 타입

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  # SSE 연결 graceful close — 드레이닝 시 스트림이 완료될 시간 부여
  deregistration_delay = 30

  tags = { Name = "${var.project_name}-tg-backend" }
}

# CloudWatch 경보 — ALB 5xx 급증 시 알림
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.project_name}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "ALB 5xx 오류 분당 10회 초과"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }
}
