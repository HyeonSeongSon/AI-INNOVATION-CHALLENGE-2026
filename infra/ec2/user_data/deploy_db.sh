#!/bin/bash
set -euo pipefail

mkdir -p /opt/db-api
python3.11 -m venv /opt/db-api/venv
aws s3 cp s3://ai-innovation-deploy/database.tar.gz /tmp/database.tar.gz
tar -xzf /tmp/database.tar.gz -C /opt/db-api
/opt/db-api/venv/bin/pip install -q -r /opt/db-api/requirements.txt
chown -R ubuntu:ubuntu /opt/db-api

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
