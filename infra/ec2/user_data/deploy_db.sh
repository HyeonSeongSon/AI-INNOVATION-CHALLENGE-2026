#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

POSTGRES_PASSWORD="ai_innovation_db"
POSTGRES_DB="ai_innovation_db"
POSTGRES_USER="postgres"
DB_API_DIR="/opt/db-api"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 1. AWS CLI
log "Installing AWS CLI..."
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
apt-get install -y -qq unzip 2>/dev/null || true
unzip -q /tmp/awscliv2.zip -d /tmp/awscli
/tmp/awscli/aws/install --update
rm -rf /tmp/awscliv2.zip /tmp/awscli
log "AWS CLI installed: $(/usr/local/bin/aws --version)"

# 2. PostgreSQL 15
log "Installing PostgreSQL 15..."
apt-get install -y -qq curl gnupg lsb-release
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
apt-get install -y -qq postgresql-15

sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/15/main/postgresql.conf
grep -q "10.0.0.0/8" /etc/postgresql/15/main/pg_hba.conf || \
  echo "host $POSTGRES_DB $POSTGRES_USER 10.0.0.0/8 md5" >> /etc/postgresql/15/main/pg_hba.conf

systemctl start postgresql
systemctl enable postgresql

sudo -u postgres psql -c "ALTER USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';"
sudo -u postgres createdb -O $POSTGRES_USER $POSTGRES_DB 2>/dev/null || true
systemctl reload postgresql
log "PostgreSQL ready."

# 3. Python + venv
log "Installing Python 3.11..."
apt-get install -y -qq python3.11 python3.11-venv python3-pip
mkdir -p "$DB_API_DIR"
python3.11 -m venv "$DB_API_DIR/venv"

# 4. 코드 배포
log "Deploying database code from S3..."
/usr/local/bin/aws s3 cp s3://ai-innovation-deploy/database.tar.gz /tmp/database.tar.gz
tar -xzf /tmp/database.tar.gz -C "$DB_API_DIR"
"$DB_API_DIR/venv/bin/pip" install -q -r "$DB_API_DIR/requirements.txt"
chown -R ubuntu:ubuntu "$DB_API_DIR"

# 5. systemd 서비스
log "Registering db-api service..."
cat > /etc/systemd/system/db-api.service <<'UNIT'
[Unit]
Description=Database API Server
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable db-api
systemctl start db-api
systemctl is-active db-api
touch /var/log/user-data-complete
log "DB setup complete."
