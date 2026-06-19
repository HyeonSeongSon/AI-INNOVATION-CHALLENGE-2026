#!/bin/bash
# OpenSearch API EC2 설치 스크립트 (임베딩 추론 전용 — opensearch_setup.sh와 분리)
# opensearch_api_server.sh (user_data 부트스트랩)이 S3에서 내려받아 실행한다.
# 환경변수는 부트스트랩에서 export된 값을 사용한다:
#   PROJECT_NAME, INTERNAL_TOKEN, OPENSEARCH_ADMIN_PASSWORD, OPENSEARCH_HOST
#
# OpenSearch 노드와 같은 인스턴스에 있던 opensearch-api(SentenceTransformer 추론,
# CPU-bound)를 별도 EC2로 분리한다 — 같은 CPU를 OpenSearch JVM 검색 스레드와
# 나눠 쓰던 경합을 없애는 목적(부하테스트 23~24차에서 확인된 CPU 포화 원인).
set -euo pipefail

OPENSEARCH_API_DIR="/opt/opensearch-api"
DATA_MOUNT="/data"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }
trap 'log "FAILED at line $LINENO (exit $?)"' ERR

# ---- 1. 시스템 업데이트 ----
log "Waiting for apt lock..."
systemctl stop unattended-upgrades apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
systemctl kill --kill-who=all apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
sleep 5
for i in $(seq 1 30); do
  if ! lsof /var/lib/dpkg/lock-frontend 2>/dev/null | grep -q dpkg; then break; fi
  log "apt lock held, waiting... ($i/30)"
  sleep 10
done

log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip

# ---- 2. EBS 데이터 볼륨 마운트 (venv 보존용) ----
log "Waiting for EBS data volume..."
DATA_DISK=""
for i in $(seq 1 24); do
  DATA_DISK=$(lsblk -d -o NAME,SIZE | awk '$2=="20G"{print "/dev/"$1}' | head -1)
  [ -n "$DATA_DISK" ] && break
  sleep 5
done
if [ -z "$DATA_DISK" ]; then
  log "ERROR: No 20GB data volume found after 2 minutes"
  exit 1
fi
log "Preparing $DATA_DISK -> $DATA_MOUNT..."
if ! blkid "$DATA_DISK" &>/dev/null; then
  mkfs.ext4 -F "$DATA_DISK"
else
  log "Running e2fsck before mount (self-heal dirty volume)..."
  e2fsck -y -f "$DATA_DISK" || log "e2fsck exit $? (corrected or non-fatal), continuing"
fi
mkdir -p "$DATA_MOUNT"
if ! mountpoint -q "$DATA_MOUNT"; then
  log "Mounting $DATA_DISK..."
  timeout 180 mount "$DATA_DISK" "$DATA_MOUNT" || log "mount returned $? (timeout/err)"
fi
if ! mountpoint -q "$DATA_MOUNT"; then
  log "ERROR: Failed to mount $DATA_DISK to $DATA_MOUNT (volume may be unrecoverable — recreate EBS)"
  exit 1
fi
grep -q "$DATA_DISK" /etc/fstab || echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab

# ---- 3. OpenSearch API venv ----
log "Setting up OpenSearch API venv..."
mkdir -p "$OPENSEARCH_API_DIR"
# EBS(/data)에 venv 보존 — EC2 재생성 후에도 재설치 스킵
if [ -f "$DATA_MOUNT/opensearch-api-venv/bin/python" ]; then
  log "EBS venv exists, skipping torch/transformers install."
else
  log "Creating venv and installing torch + transformers..."
  python3.11 -m venv "$DATA_MOUNT/opensearch-api-venv"
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q --upgrade pip
  # CPU-only torch: CUDA 2GB 방지
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
  # transformers 4.41.0: 5.x에서 sentence-transformers + torch._dynamo 충돌
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q "transformers==4.41.0"
fi
touch /var/log/venv-ready
chown -R ubuntu:ubuntu "$OPENSEARCH_API_DIR" "$DATA_MOUNT/opensearch-api-venv"

# ---- 4. OpenSearch API systemd 서비스 ----
log "Registering opensearch-api service..."
cat > /etc/systemd/system/opensearch-api.service <<UNIT
[Unit]
Description=OpenSearch API Server (ai-innovation)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/opensearch-api
Environment=OPENSEARCH_URL=https://$OPENSEARCH_HOST:9200
Environment=OPENSEARCH_HOST=$OPENSEARCH_HOST
Environment=OPENSEARCH_PORT=9200
Environment=OPENSEARCH_USE_SSL=true
Environment=OPENSEARCH_ADMIN_PASSWORD=$OPENSEARCH_ADMIN_PASSWORD
Environment=INTERNAL_TOKEN=$INTERNAL_TOKEN
Environment=FORBIDDEN_KEYWORD_JSON_PATH=/opt/opensearch-api/data/forbidden_keyword.json
ExecStart=$DATA_MOUNT/opensearch-api-venv/bin/uvicorn opensearch_api:app --host 0.0.0.0 --port 8010 --workers 1
TimeoutStartSec=120
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=opensearch-api

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable opensearch-api
# 이 시점엔 /opt/opensearch-api에 코드가 아직 없음(CI의 별도 SSM 배포 단계에서 채워짐) —
# 서비스 기동은 그 배포 단계의 마지막에 systemctl restart로 수행.

log "OpenSearch API setup complete."
touch /var/log/user-data-complete
