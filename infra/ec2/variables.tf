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

variable "opensearch_setup_hash" {
  description = <<-EOT
    opensearch_setup.sh 내용 해시. CI가 sha256으로 계산해 주입한다.
    S3 키(opensearch_setup.<hash>.sh)와 부트스트랩 user_data에 함께 들어가므로
    setup.sh가 바뀌면 EC2가 자동 교체되고, 부트스트랩은 정확히 그 버전만 내려받는다.
    (S3 latest 키를 받던 race condition 제거 + 수동 SETUP_REVISION 불필요)
  EOT
  type        = string
  default     = "dev"
}

variable "opensearch_api_setup_hash" {
  description = "opensearch_api_setup.sh 내용 해시 — opensearch_setup_hash와 동일한 버전 키화 패턴"
  type        = string
  default     = "dev"
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
  description = <<-EOT
    OpenSearch EC2 인스턴스 타입. opensearch-api(임베딩 추론)는 별도 EC2로 분리되어
    이 인스턴스엔 OpenSearch JVM(~1.5GB)만 상주 — t3.medium(4GB)+swap로 충분히 여유.
    (과거 색인 크래시는 메모리가 아니라 knn nmslib 네이티브 미탑재 문제였고 lucene 엔진으로 해결됨)
  EOT
  type        = string
  default     = "t3.medium"
}

variable "opensearch_api_instance_type" {
  description = <<-EOT
    OpenSearch API(임베딩 추론, KURE-v1) 전용 EC2 인스턴스 타입.
    CPU-바운드 인코딩 워크로드라 vCPU 수가 핵심 — t3.medium/t3.large는 둘 다 2 vCPU로
    동일해서 패밀리 내 단순 업그레이드는 효과가 없다(메모리만 늘어남). c5.xlarge(4 vCPU,
    컴퓨트 최적화)로 vCPU를 실제로 2배 늘리고, t3 버스터블 인스턴스의 CPU 크레딧 소진에
    따른 스로틀링 리스크도 같이 없앤다(25차 부하테스트에서 본 지속적 100% CPU 부하는
    버스터블 인스턴스에 불리한 패턴).
  EOT
  type        = string
  default     = "c5.xlarge"
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

variable "opensearch_api_az" {
  description = "OpenSearch API EBS(venv 보존) 고정 AZ — EC2 재생성 시 EBS가 다른 AZ로 옮겨지지 않도록 고정"
  type        = string
  default     = "ap-northeast-2a"
}

variable "opensearch_api_ebs_volume_size_gb" {
  description = <<-EOT
    OpenSearch API venv 보존용 EBS 볼륨 크기 (GB) — torch/transformers만 담으므로
    OpenSearch/DB보다 작게. 루트 볼륨(20GB)과 다른 크기여야 한다 — 디스크 탐지
    스크립트(opensearch_api_setup.sh)가 lsblk 사이즈로 데이터 볼륨을 구분하므로
    같은 크기면 루트 볼륨을 잘못 마운트한다. EBS는 축소가 불가능(AWS 제약)하므로
    반드시 루트 볼륨(20GB)보다 큰 값을 써야 한다 — 작게 가면 in-place resize가
    "New size cannot be smaller than existing size" 에러로 실패한다.
  EOT
  type        = number
  default     = 25
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

variable "opensearch_admin_password" {
  description = "OpenSearch admin 비밀번호 (최소 8자, 대소문자+숫자+특수문자 포함)"
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
