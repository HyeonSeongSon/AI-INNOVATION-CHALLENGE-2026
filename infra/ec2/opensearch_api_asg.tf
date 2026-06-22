# -----------------------------------------------------------------------
# OpenSearch API — 단일 EC2 → Auto Scaling Group 전환
#
# 32~33차 부하테스트에서 opensearch-api(임베딩 인코딩 전담) EC2의 CPU가 반복적으로
# 99%대까지 포화됐다. 워커를 늘리지 않는 이유(opensearch_api.py:192 — 모델을 워커마다
# 따로 로드하면 메모리가 배수로 늘어남)는 그대로 유지하고, 인스턴스 수로 확장한다.
#
# 코드/venv/모델/데이터를 전부 포함한 "골든 AMI"를 빌드 시점(CI, deploy.yml)에 굽고,
# ASG는 항상 그 AMI로만 인스턴스를 띄운다 — 그래야 새 인스턴스가 부팅 직후 코드 없이
# 크래시 루프에 빠지는 일이 없다(opensearch_api_setup.sh:118 주석이 명시하는 문제:
# "이 시점엔 /opt/opensearch-api에 코드가 아직 없음" — 단일 EC2에서는 SSM 배포가 뒤따라와
# 문제가 안 됐지만, ASG가 매번 새로 부팅하는 인스턴스에는 그 SSM 단계가 없다).
# -----------------------------------------------------------------------

resource "aws_launch_template" "opensearch_api" {
  name_prefix            = "${var.project_name}-lt-opensearch-api-"
  image_id               = var.opensearch_api_golden_ami_id != "" ? var.opensearch_api_golden_ami_id : var.ec2_ami
  instance_type          = var.opensearch_api_instance_type
  key_name               = var.ec2_key_name != "" ? var.ec2_key_name : null
  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  # subnet_id를 여기 network_interfaces에 박아둔다 — CI가 빌더를 띄울 때
  # (aws ec2 run-instances --launch-template, ASG 밖에서 단독 실행) subnet을 따로 지정하지
  # 않아도 항상 ASG와 같은 서브넷/보안그룹으로 뜬다. subnet 없이 vpc_security_group_ids만
  # 쓰면 AWS가 기본 VPC의 기본 서브넷으로 보내버려 "보안그룹과 서브넷이 다른 네트워크"
  # 에러가 난다.
  network_interfaces {
    associate_public_ip_address = false
    subnet_id                   = aws_subnet.private[0].id
    security_groups             = [aws_security_group.opensearch_api_ec2.id]
  }

  # 평소엔 가벼운 경로(시크릿/피어 IP를 env 파일에 써주고 서비스 재시작)만 탄다 — 무거운
  # 설치(apt/venv/torch/모델/코드)는 골든 AMI에 이미 포함돼 있다. 골든 AMI가 아직 없는
  # 최초 상태(launch template이 베이스 AMI를 가리킬 때)에만 콜드 폴백으로 무거운 설치를
  # 탄다(opensearch_api_asg_boot.sh 주석 참고) — 그래서 project_name/setup_hash도 같이 넘긴다.
  user_data = base64encode(templatefile("${path.module}/user_data/opensearch_api_asg_boot.sh", {
    project_name              = var.project_name
    setup_hash                = var.opensearch_api_setup_hash
    internal_token            = var.internal_token
    opensearch_admin_password = var.opensearch_admin_password
    opensearch_host           = aws_instance.opensearch.private_ip
  }))

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.project_name}-ec2-opensearch-api-asg" }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "opensearch_api" {
  name                = "${var.project_name}-asg-opensearch-api"
  vpc_zone_identifier = [aws_subnet.private[0].id] # 단일 AZ 유지 — OpenSearch 검색 클러스터 자체가 단일 AZ라 멀티 AZ로 가도 실질 가용성이 안 늘어남
  min_size            = 1
  max_size            = var.opensearch_api_asg_max_size
  desired_capacity    = 1

  health_check_type         = "ELB"
  health_check_grace_period = 90 # 골든 AMI라 venv/모델 재설치·재다운로드 없음 — 부팅+EBS 마운트+서비스 기동만 고려

  target_group_arns = [aws_lb_target_group.opensearch_api.arn]

  launch_template {
    id      = aws_launch_template.opensearch_api.id
    version = "$Latest" # CI가 create-launch-template-version으로 새 버전을 만들면 자동으로 따라간다 — Terraform이 버전을 별도로 추적하지 않아 드리프트가 없음
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-ec2-opensearch-api-asg"
    propagate_at_launch = true
  }

  # instance_refresh 블록은 의도적으로 추가하지 않음 — CI(deploy.yml)가
  # aws autoscaling start-instance-refresh로 명시적으로 트리거하고 완료를 폴링한다.
  # Terraform 쪽 트리거를 같이 켜면 같은 변경에 리프레시가 중복 발생할 수 있다.
}

resource "aws_autoscaling_policy" "opensearch_api_cpu" {
  name                   = "${var.project_name}-asg-opensearch-api-cpu-target-tracking"
  autoscaling_group_name = aws_autoscaling_group.opensearch_api.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 62.0 # 32~33차에서 99%대 포화가 반복됐으므로 충분히 낮은 임계치로 시작
  }
}
