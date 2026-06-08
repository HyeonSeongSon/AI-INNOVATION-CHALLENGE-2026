variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "environment" {
  description = "환경 이름 (production / staging)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "리소스 이름 접두사"
  type        = string
  default     = "ai-innovation"
}

# ---- 네트워크 ----

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "퍼블릭 서브넷 CIDR 목록 (ALB, NAT GW 배치)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "프라이빗 서브넷 CIDR 목록 (ECS, EC2 배치)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "availability_zones" {
  description = "배포 가용 영역 목록"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

# ---- EC2 ----

variable "db_instance_type" {
  description = "PostgreSQL EC2 인스턴스 타입"
  type        = string
  default     = "t3.medium"
}

variable "opensearch_instance_type" {
  description = "OpenSearch EC2 인스턴스 타입"
  type        = string
  default     = "t3.medium"
}

variable "ec2_ami" {
  description = "Ubuntu 22.04 LTS AMI (ap-northeast-2)"
  type        = string
  default     = "ami-0c9c942bd7bf113a2"
}

variable "ec2_key_name" {
  description = "EC2 SSH 키 페어 이름 (빈 문자열이면 키 없이 생성)"
  type        = string
  default     = ""
}

variable "ebs_volume_size_gb" {
  description = "데이터 EBS 볼륨 크기 (GB) — PostgreSQL, OpenSearch 각각 적용"
  type        = number
  default     = 50
}

variable "db_az" {
  description = "DB EBS 고정 AZ — EC2 재생성 시 EBS가 다른 AZ로 옮겨지지 않도록 고정"
  type        = string
  default     = "ap-northeast-2a"
}

variable "opensearch_az" {
  description = "OpenSearch EBS 고정 AZ — EC2 재생성 시 EBS가 다른 AZ로 옮겨지지 않도록 고정"
  type        = string
  default     = "ap-northeast-2a"
}

# ---- ECS ----

variable "ecs_task_cpu" {
  description = "ECS 태스크 CPU 유닛 (1 vCPU = 1024)"
  type        = number
  default     = 512
}

variable "ecs_task_memory" {
  description = "ECS 태스크 메모리 (MB)"
  type        = number
  default     = 1024
}

variable "ecr_image_tag" {
  description = "배포할 Docker 이미지 태그"
  type        = string
  default     = "latest"
}

variable "ecr_registry" {
  description = "ECR 레지스트리 URI (예: 123456789012.dkr.ecr.ap-northeast-2.amazonaws.com)"
  type        = string
}

variable "ecs_service_desired_count" {
  description = "각 ECS 서비스 기본 태스크 수"
  type        = number
  default     = 1
}

# ---- ALB ----

variable "alb_ssl_certificate_arn" {
  description = "HTTPS용 ACM 인증서 ARN (빈 문자열이면 HTTP만 사용)"
  type        = string
  default     = ""
}

# ---- 시크릿 (민감 정보) ----

variable "postgres_password" {
  description = "PostgreSQL 비밀번호"
  type        = string
  sensitive   = true
}

variable "internal_token" {
  description = "내부 서비스 간 인증 토큰 (최소 32자, openssl rand -hex 32)"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT 서명 시크릿 (최소 32자, openssl rand -hex 32)"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API 키 (GPT 모델 사용 시 필수)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API 키 (Claude 모델 사용 시 필수)"
  type        = string
  sensitive   = true
  default     = ""
}

# ---- 앱 설정 ----

variable "allowed_origins" {
  description = "CORS 허용 오리진 (콤마 구분, 예: https://example.com)"
  type        = string
  default     = ""
}

variable "chatgpt_model_name" {
  description = "메인 LLM 모델명"
  type        = string
  default     = "gpt-5-mini"
}

variable "parser_model_name" {
  description = "파서 LLM 모델명"
  type        = string
  default     = "gpt-5-nano"
}

# ---- Admin 시드 ----

variable "admin_seed_email" {
  description = "최초 배포 시 생성할 admin 이메일 (시드 후 Secrets Manager에서 삭제)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_seed_password" {
  description = "최초 배포 시 생성할 admin 비밀번호 (시드 후 Secrets Manager에서 삭제)"
  type        = string
  sensitive   = true
  default     = ""
}
