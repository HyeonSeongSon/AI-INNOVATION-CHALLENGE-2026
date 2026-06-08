#!/bin/bash
# -----------------------------------------------------------------------
# OpenSearch EC2 user_data: OpenSearch 2.x + OpenSearch API (port 8010)
#
# 메모리 예산 (t3.medium RAM 4GB / 3863MB usable):
#   OpenSearch JVM heap: 1000m  (실사용 ~1200MB)
#   opensearch-api + KURE-v1 모델: ~1500MB
#   OS + 커널 + SSM 에이전트: ~600MB
#   여유 (스왑): ~563MB → 4GB 스왑으로 보완
#
# 중요: JVM을 1500m으로 설정하면 KURE-v1 로드 후 SSM 에이전트가
# OOM으로 종료됩니다. 반드시 1000m을 유지하세요.
# -----------------------------------------------------------------------
set -euo pipefail

PROJECT_NAME="${project_name}"
OPENSEARCH_VERSION="${OPENSEARCH_VERSION}"
OPENSEARCH_API_DIR="/opt/opensearch-api"
DATA_MOUNT="/data"
INTERNAL_TOKEN="${internal_token}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }

# ---- 1. 시스템 업데이트 ----
log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl gnupg unzip openjdk-17-jdk python3.11 python3.11-venv python3-pip git

# ---- AWS CLI 설치 ----
log "Installing AWS CLI..."
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

# ---- 2. EBS 데이터 볼륨 마운트 ----
log "Waiting for data volume to be attached..."
DATA_DISK=""
for i in $(seq 1 24); do
  DATA_DISK=$(lsblk -d -o NAME,SIZE | awk '$2=="50G"{print "/dev/"$1}' | head -1)
  [ -n "$DATA_DISK" ] && break
  sleep 5
done
if [ -z "$DATA_DISK" ]; then
  log "ERROR: No 50GB data volume found after 2 minutes"
  exit 1
fi
log "Mounting data volume $DATA_DISK -> $DATA_MOUNT..."
if ! blkid "$DATA_DISK" &>/dev/null; then
  mkfs.ext4 -F "$DATA_DISK"
fi
mkdir -p "$DATA_MOUNT"
mount "$DATA_DISK" "$DATA_MOUNT" || true
grep -q "$DATA_DISK" /etc/fstab || echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab

# ---- 3. 스왑 파일 추가 (인덱싱 중 OOM 방지) ----
log "Setting up 4GB swap file..."
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
fi
swapon /swapfile 2>/dev/null || true
grep -q swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab

# ---- 4. OS 파라미터 조정 (OpenSearch 필수) ----
log "Tuning OS parameters for OpenSearch..."
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" >> /etc/sysctl.conf
echo "opensearch soft nofile 65536" >> /etc/security/limits.conf
echo "opensearch hard nofile 65536" >> /etc/security/limits.conf

# ---- 5. OpenSearch 설치 ----
log "Installing OpenSearch $OPENSEARCH_VERSION..."
curl -fsSL "https://artifacts.opensearch.org/releases/bundle/opensearch/$${OPENSEARCH_VERSION}/opensearch-$${OPENSEARCH_VERSION}-linux-x64.tar.gz" \
  -o /tmp/opensearch.tar.gz
mkdir -p /opt/opensearch
tar xzf /tmp/opensearch.tar.gz -C /opt/opensearch --strip-components=1
rm /tmp/opensearch.tar.gz

# 데이터/로그를 EBS 볼륨으로 설정
mkdir -p "$DATA_MOUNT/opensearch/data" "$DATA_MOUNT/opensearch/logs"
useradd -r -s /bin/false opensearch 2>/dev/null || true
chown -R opensearch:opensearch /opt/opensearch "$DATA_MOUNT/opensearch"

# opensearch.yml
cat > /opt/opensearch/config/opensearch.yml <<EOF
cluster.name: $PROJECT_NAME-search
node.name: node-1
path.data: $DATA_MOUNT/opensearch/data
path.logs: $DATA_MOUNT/opensearch/logs
network.host: 0.0.0.0
http.port: 9200
discovery.type: single-node
plugins.security.disabled: true
EOF

# -----------------------------------------------------------------------
# JVM heap 1000m 설정 — 반드시 1000m 이하로 유지
# 1500m으로 설정하면 KURE-v1(~1500MB) 로드 후 SSM 에이전트가
# OOM으로 종료되어 GitHub Actions 배포가 불가능해집니다.
# -----------------------------------------------------------------------
sed -i 's/-Xms[0-9]*[gGmM]/-Xms1000m/g' /opt/opensearch/config/jvm.options
sed -i 's/-Xmx[0-9]*[gGmM]/-Xmx1000m/g' /opt/opensearch/config/jvm.options
grep -q "Xms" /opt/opensearch/config/jvm.options || echo "-Xms1000m" >> /opt/opensearch/config/jvm.options
grep -q "Xmx" /opt/opensearch/config/jvm.options || echo "-Xmx1000m" >> /opt/opensearch/config/jvm.options

# ---- 6. OpenSearch systemd 서비스 등록 ----
log "Registering opensearch systemd service..."
cat > /etc/systemd/system/opensearch.service <<'UNIT'
[Unit]
Description=OpenSearch (ai-innovation)
After=network.target

[Service]
Type=simple
User=opensearch
Group=opensearch
WorkingDirectory=/opt/opensearch
ExecStart=/opt/opensearch/bin/opensearch
LimitNOFILE=65536
LimitMEMLOCK=infinity
Restart=always
RestartSec=10
StartLimitIntervalSec=180
StartLimitBurst=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=opensearch

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable opensearch
systemctl start opensearch

# OpenSearch 준비 대기 (최대 120초)
log "Waiting for OpenSearch to be ready..."
for i in $(seq 1 24); do
  if curl -sf http://localhost:9200/_cluster/health &>/dev/null; then
    log "OpenSearch is ready."
    break
  fi
  sleep 5
done

# 플러그인 설치: 한국어 형태소 분석기 + KNN + S3 스냅샷
/opt/opensearch/bin/opensearch-plugin install --batch analysis-nori || true
/opt/opensearch/bin/opensearch-plugin install --batch opensearch-knn || true
/opt/opensearch/bin/opensearch-plugin install --batch repository-s3 || true
systemctl restart opensearch

# ---- 7. OpenSearch API 서비스 설치 ----
log "Installing OpenSearch API server..."
mkdir -p "$OPENSEARCH_API_DIR"
# venv는 EBS(/data)에 생성 — 루트 디스크(20GB) 용량 부족 방지
python3.11 -m venv "$DATA_MOUNT/opensearch-api-venv"
# CPU-only torch + transformers 4.x 사전 설치
# - torch: CPU 버전으로 CUDA 2GB 다운로드 방지
# - transformers==4.41.0: 5.x 설치 시 sentence-transformers와 torch._dynamo 충돌 방지
"$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q --upgrade pip
"$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
"$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q "transformers==4.41.0"
chown -R ubuntu:ubuntu "$OPENSEARCH_API_DIR" "$DATA_MOUNT/opensearch-api-venv"

# ---- 8. OpenSearch API systemd 서비스 등록 ----
log "Registering opensearch-api systemd service..."
cat > /etc/systemd/system/opensearch-api.service <<UNIT
[Unit]
Description=OpenSearch API Server (ai-innovation)
After=opensearch.service
Requires=opensearch.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/opensearch-api
Environment=OPENSEARCH_URL=http://localhost:9200
Environment=OPENSEARCH_HOST=localhost
Environment=OPENSEARCH_PORT=9200
Environment=OPENSEARCH_ADMIN_PASSWORD=admin
Environment=INTERNAL_TOKEN=$INTERNAL_TOKEN
# OpenSearch 완전 기동 후 60초 추가 대기
# — 재부팅 직후 SSM 에이전트가 메모리를 확보할 시간을 확보합니다
ExecStartPre=/bin/sleep 60
ExecStart=$DATA_MOUNT/opensearch-api-venv/bin/uvicorn opensearch_api:app --host 0.0.0.0 --port 8010 --workers 2
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
# 코드는 GitHub Actions SSM 배포에서 설치 후 시작

log "OpenSearch server setup complete."
log "  OpenSearch:     systemctl status opensearch"
log "  OpenSearch API: systemctl status opensearch-api"
touch /var/log/user-data-complete
