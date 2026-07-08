# -----------------------------------------------------------------------
# EC2 인스턴스 — PostgreSQL + Database API / OpenSearch + OpenSearch API
#
# 각 EC2에는 루트 볼륨(OS)과 별도 EBS 데이터 볼륨이 연결됩니다.
# EC2를 교체하거나 AMI를 업데이트해도 데이터 볼륨은 보존됩니다.
# -----------------------------------------------------------------------

# ---- IAM Role (SSM Session Manager로 SSH 없이 접근) ----

resource "aws_iam_role" "ec2" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# S3 deploy 버킷 권한 — 코드 pull(읽기) + OpenSearch 스냅샷(쓰기)
resource "aws_iam_role_policy" "ec2_s3_deploy" {
  name = "${var.project_name}-ec2-s3-deploy"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.deploy.arn,
          "${aws_s3_bucket.deploy.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:DeleteObject"]
        Resource = [
          "${aws_s3_bucket.deploy.arn}/opensearch-snapshots/*",
          "${aws_s3_bucket.deploy.arn}/backups/*",
        ]
      }
    ]
  })
}

# Secrets Manager 읽기 — db-api .env 주입용
resource "aws_iam_role_policy" "ec2_secrets" {
  name = "${var.project_name}-ec2-secrets"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*"
    }]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2.name
}

# ---- DB EC2 — PostgreSQL 15 + Database API (port 8020) ----

resource "aws_instance" "db" {
  ami                         = var.ec2_ami
  instance_type               = var.db_instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.db_ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  key_name                    = var.ec2_key_name != "" ? var.ec2_key_name : null
  user_data_replace_on_change = true

  user_data = base64encode(templatefile("${path.module}/user_data/db_server.sh", {
    postgres_password = var.postgres_password
    project_name      = var.project_name
  }))

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "${var.project_name}-ec2-db" }
}

# DB 데이터 볼륨 (루트와 분리 — EC2 교체 시에도 데이터 유지)
# lifecycle.prevent_destroy = true — EC2 재생성 시 EBS 삭제 방지
resource "aws_ebs_volume" "db_data" {
  availability_zone = var.db_az
  size              = var.ebs_volume_size_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name   = "${var.project_name}-ebs-db-data"
    Backup = "true" # DLM 일일 스냅샷 대상 (backup.tf)
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_volume_attachment" "db_data" {
  device_name  = "/dev/xvdf"
  volume_id    = aws_ebs_volume.db_data.id
  instance_id  = aws_instance.db.id
  force_detach = true
}

# ---- OpenSearch EC2 — OpenSearch 2.x + OpenSearch API (port 8010) ----

resource "aws_instance" "opensearch" {
  ami                         = var.ec2_ami
  instance_type               = var.opensearch_instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.opensearch_ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  key_name                    = var.ec2_key_name != "" ? var.ec2_key_name : null
  user_data_replace_on_change = true

  user_data = base64encode(templatefile("${path.module}/user_data/opensearch_server.sh", {
    project_name              = var.project_name
    OPENSEARCH_VERSION        = "2.13.0"
    internal_token            = var.internal_token
    opensearch_admin_password = var.opensearch_admin_password
    setup_hash                = var.opensearch_setup_hash
  }))

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "${var.project_name}-ec2-opensearch" }
}

# OpenSearch 데이터 볼륨
# lifecycle.prevent_destroy = true — EC2 재생성(user_data_replace_on_change) 시 EBS 삭제 방지
resource "aws_ebs_volume" "opensearch_data" {
  availability_zone = var.opensearch_az
  size              = var.ebs_volume_size_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name   = "${var.project_name}-ebs-opensearch-data"
    Backup = "true" # DLM 일일 스냅샷 대상 (backup.tf)
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_volume_attachment" "opensearch_data" {
  device_name  = "/dev/xvdf"
  volume_id    = aws_ebs_volume.opensearch_data.id
  instance_id  = aws_instance.opensearch.id
  force_detach = true
}

# ---- OpenSearch API EC2 — 임베딩 추론(SentenceTransformer) 전용, OpenSearch 노드와 분리 ----
# CPU 경합 해소 목적(부하테스트 23~24차에서 OpenSearch 노드와 같은 인스턴스에서 돌던
# opensearch-api의 인코딩이 OpenSearch JVM 검색 스레드의 CPU를 빼앗는 현상을 확인).

resource "aws_instance" "opensearch_api" {
  ami                         = var.ec2_ami
  instance_type               = var.opensearch_api_instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.opensearch_api_ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  key_name                    = var.ec2_key_name != "" ? var.ec2_key_name : null
  user_data_replace_on_change = true

  user_data = base64encode(templatefile("${path.module}/user_data/opensearch_api_server.sh", {
    project_name              = var.project_name
    internal_token            = var.internal_token
    opensearch_admin_password = var.opensearch_admin_password
    opensearch_host           = aws_instance.opensearch.private_ip
    setup_hash                = var.opensearch_api_setup_hash
  }))

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "${var.project_name}-ec2-opensearch-api" }
}

# OpenSearch API venv 보존 볼륨 (torch/transformers — EC2 교체 시에도 재설치 스킵)
resource "aws_ebs_volume" "opensearch_api_data" {
  availability_zone = var.opensearch_api_az
  size              = var.opensearch_api_ebs_volume_size_gb
  type              = "gp3"
  encrypted         = true

  tags = {
    Name   = "${var.project_name}-ebs-opensearch-api-data"
    Backup = "true"
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_volume_attachment" "opensearch_api_data" {
  device_name  = "/dev/xvdf"
  volume_id    = aws_ebs_volume.opensearch_api_data.id
  instance_id  = aws_instance.opensearch_api.id
  force_detach = true
}

# ---- S3 Deploy 버킷 (앱 코드 아카이브 저장) ----

resource "aws_s3_bucket" "deploy" {
  bucket = "${var.project_name}-deploy"
}

resource "aws_s3_bucket_versioning" "deploy" {
  bucket = aws_s3_bucket.deploy.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket                  = aws_s3_bucket.deploy.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 백업 보관 정책 — pg_dump 논리 백업(backups/)은 30일 후 만료
resource "aws_s3_bucket_lifecycle_configuration" "deploy" {
  bucket = aws_s3_bucket.deploy.id

  rule {
    id     = "expire-postgres-backups"
    status = "Enabled"

    filter {
      prefix = "backups/"
    }

    expiration {
      days = 30
    }
  }
}
