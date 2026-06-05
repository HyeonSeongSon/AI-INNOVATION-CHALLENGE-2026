variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "리소스 이름 접두사"
  type        = string
  default     = "ai-innovation"
}

variable "github_org" {
  description = "GitHub 조직 또는 사용자명 (예: myorg)"
  type        = string
}

variable "github_repo" {
  description = "GitHub 레포지토리명 (예: AI-INNOVATION-CHALLENGE-2026)"
  type        = string
}
