#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
POSTGRES_PASSWORD="ai_innovation_db"
POSTGRES_DB="ai_innovation_db"
POSTGRES_USER="postgres"

# PostgreSQL 15 설치
apt-get install -y -qq curl gnupg lsb-release
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq postgresql-15

# VPC 내부 접근 허용
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/15/main/postgresql.conf
cat >> /etc/postgresql/15/main/pg_hba.conf <<EOF
host    $POSTGRES_DB    $POSTGRES_USER    10.0.0.0/8    md5
EOF

systemctl start postgresql
systemctl enable postgresql

# DB 및 사용자 설정
sudo -u postgres psql <<SQL
ALTER USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';
SELECT 'CREATE DATABASE $POSTGRES_DB' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$POSTGRES_DB')\gexec
SQL

sudo -u postgres createdb -O $POSTGRES_USER $POSTGRES_DB 2>/dev/null || true
systemctl reload postgresql

# db-api 서비스의 Requires=postgresql.service 제거 후 재시작
sed -i '/Requires=postgresql.service/d' /etc/systemd/system/db-api.service
sed -i 's/After=postgresql.service/After=network.target/' /etc/systemd/system/db-api.service
systemctl daemon-reload
systemctl start db-api
systemctl is-active db-api
