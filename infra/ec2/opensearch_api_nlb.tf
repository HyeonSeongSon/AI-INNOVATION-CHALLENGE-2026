# -----------------------------------------------------------------------
# 내부 NLB — ECS 태스크 → OpenSearch API ASG 인스턴스 분산
#
# 기존엔 ECS 태스크가 opensearch_api EC2의 고정 private IP를 직접 호출했다(ecs.tf).
# ASG로 전환하면서 인스턴스가 여러 개·수시로 바뀌므로, 내부 NLB가 그 사이를 가로막는다.
# ALB(alb.tf)와 달리 이건 외부에 노출되지 않는 VPC 내부 전용이라 NLB + target_type=instance로 둔다.
# -----------------------------------------------------------------------

resource "aws_lb" "opensearch_api" {
  name               = "${var.project_name}-nlb-opensearch-api"
  internal           = true
  load_balancer_type = "network"
  subnets            = [aws_subnet.private[0].id] # ASG와 동일 서브넷

  tags = { Name = "${var.project_name}-nlb-opensearch-api" }
}

resource "aws_lb_target_group" "opensearch_api" {
  name        = "${var.project_name}-tg-opensearch-api"
  port        = 8010
  protocol    = "TCP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  health_check {
    protocol            = "HTTP"
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    matcher             = "200"
  }

  # 인코딩 요청은 SSE처럼 길게 끌지 않으므로 ALB 백엔드 타깃그룹(30s)보다 짧게 둔다 —
  # 진행 중인 짧은 요청이 끊기지 않을 정도면 충분.
  deregistration_delay = 15

  tags = { Name = "${var.project_name}-tg-opensearch-api" }
}

resource "aws_lb_listener" "opensearch_api" {
  load_balancer_arn = aws_lb.opensearch_api.arn
  port              = 8010
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.opensearch_api.arn
  }
}
