#!/bin/bash
# -----------------------------------------------------------------------
# [이슈 4] DB EC2 user_data: PostgreSQL 15 + Database API (port 8020)
#
# EC2 최초 부팅 시 cloud-init이 root 권한으로 실행합니다.
# db-api.service는 postgresql.service에 의존하므로
# PostgreSQL이 죽으면 db-api도 함께 재시작됩니다.
# -----------------------------------------------------------------------
set -euo pipefail

PROJECT_NAME="${project_name}"
POSTGRES_PASSWORD="${postgres_password}"
DB_API_DIR="/opt/db-api"
DATA_DISK=$(lsblk -d -o NAME,SIZE | awk '$2=="50G"{print "/dev/"$1}' | head -1)
DATA_MOUNT="/data"
POSTGRES_DB="ai_innovation_db"
POSTGRES_USER="postgres"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }

# ---- 1. 시스템 업데이트 ----
log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# ---- 2. EBS 데이터 볼륨 마운트 ----
log "Mounting data volume $DATA_DISK -> $DATA_MOUNT..."
if ! blkid "$DATA_DISK" &>/dev/null; then
  mkfs.ext4 -F "$DATA_DISK"
fi
mkdir -p "$DATA_MOUNT"
mount "$DATA_DISK" "$DATA_MOUNT" || true
# /etc/fstab에 등록 — 재부팅 후 자동 마운트
grep -q "$DATA_DISK" /etc/fstab || echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab

# ---- 3. PostgreSQL 15 설치 ----
log "Installing PostgreSQL 15..."
apt-get install -y -qq curl gnupg lsb-release
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq postgresql-15

# PostgreSQL 데이터 디렉터리를 EBS 볼륨으로 이동
systemctl stop postgresql || true
mkdir -p "$DATA_MOUNT/postgresql/15/main"
if [ -d /var/lib/postgresql/15/main ] && [ "$(ls -A /var/lib/postgresql/15/main)" ]; then
  rsync -a /var/lib/postgresql/ "$DATA_MOUNT/postgresql/"
fi
chown -R postgres:postgres "$DATA_MOUNT/postgresql"
sed -i "s|/var/lib/postgresql|$DATA_MOUNT/postgresql|g" /etc/postgresql/15/main/postgresql.conf

# VPC 내부(10.0.0.0/8) 접근 허용
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/15/main/postgresql.conf
cat >> /etc/postgresql/15/main/pg_hba.conf <<EOF
host    $POSTGRES_DB    $POSTGRES_USER    10.0.0.0/8    md5
EOF

systemctl start postgresql
systemctl enable postgresql

# DB 및 사용자 설정
sudo -u postgres psql <<SQL
ALTER USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';
SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB' OR pg_catalog.pg_database.datname = '$POSTGRES_DB' \gset
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = '$POSTGRES_DB') THEN
    PERFORM dblink_exec('', 'CREATE DATABASE $POSTGRES_DB');
  END IF;
END;
\$\$;
SQL
sudo -u postgres createdb -O $POSTGRES_USER $POSTGRES_DB 2>/dev/null || true

systemctl reload postgresql

# ---- 4. AWS CLI 설치 ----
log "Installing AWS CLI..."
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
apt-get install -y -qq unzip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

# ---- 5. Python 3.11 + venv 설치 ----
log "Installing Python 3.11..."
apt-get install -y -qq python3.11 python3.11-venv python3-pip git

mkdir -p "$DB_API_DIR"
python3.11 -m venv "$DB_API_DIR/venv"
chown -R ubuntu:ubuntu "$DB_API_DIR"

# ---- 5. systemd 서비스 등록 ----
log "Registering db-api systemd service..."
cat > /etc/systemd/system/db-api.service <<'UNIT'
[Unit]
Description=Database API Server (ai-innovation)
Documentation=https://github.com/ai-innovation-challenge/database
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/db-api
ExecStart=/opt/db-api/venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8020 --workers 2
Restart=always
RestartSec=5
# 연속 실패 시 재시작 주기를 늘려 플래핑 방지
StartLimitIntervalSec=120
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=db-api

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable db-api
# 코드는 GitHub Actions SSM 배포에서 설치 후 시작

log "DB server setup complete."
log "  PostgreSQL: systemctl status postgresql"
log "  DB API:     systemctl status db-api"
touch /var/log/user-data-complete
