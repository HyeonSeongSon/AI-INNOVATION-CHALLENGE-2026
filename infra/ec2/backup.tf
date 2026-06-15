# -----------------------------------------------------------------------
# 백업 — 계층형 (프로덕션 표준)
#
# 1계층(이 파일): DLM EBS 스냅샷 — DB·OpenSearch 데이터 볼륨 블록 레벨 일일 스냅샷.
#                재해 복구(DR)/전체 복구용. crash-consistent.
# 2계층(user_data): 논리 백업 — Postgres pg_dump → S3, OpenSearch _snapshot → S3.
#                  테이블·인덱스 단위 granular 복구용.
#
# 대상 볼륨은 ec2.tf의 aws_ebs_volume에 Backup="true" 태그로 선택한다.
# -----------------------------------------------------------------------

# ---- DLM 서비스 역할 ----

resource "aws_iam_role" "dlm" {
  name = "${var.project_name}-dlm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

# ---- DLM 라이프사이클 정책 — 데이터 EBS 볼륨 일일 스냅샷 ----

resource "aws_dlm_lifecycle_policy" "ebs_daily" {
  description        = "${var.project_name} 데이터 볼륨 일일 EBS 스냅샷 (DB + OpenSearch)"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    # ec2.tf의 두 데이터 볼륨이 공유하는 태그로 선택
    target_tags = {
      Backup = "true"
    }

    schedule {
      name = "daily-7d"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["18:00"] # UTC = KST 03:00 (저트래픽)
      }

      retain_rule {
        count = 7
      }

      tags_to_add = {
        SnapshotCreator = "dlm"
      }

      copy_tags = true
    }
  }
}
