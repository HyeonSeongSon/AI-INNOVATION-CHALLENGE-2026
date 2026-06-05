#!/bin/bash
# -----------------------------------------------------------------------
# [이슈 4] OpenSearch EC2 user_data: OpenSearch 2.x + OpenSearch API (port 8010)
#
# JVM heap을 1500m으로 제한합니다 (t3.medium RAM 4GB 배분):
#   OpenSearch JVM: 1500m
#   OS + 커널:       500m
#   opensearch-api:  ~300m
#   여유:            ~1700m  ← OOM 방지 버퍼
#
# opensearch-api.service는 opensearch.service에 의존하므로
# OpenSearch가 죽으면 API 서버도 함께 재시작됩니다.
# -----------------------------------------------------------------------
set -euo pipefail

PROJECT_NAME="${project_name}"
OPENSEARCH_VERSION="2.13.0"
OPENSEARCH_API_DIR="/opt/opensearch-api"
DATA_DISK="/dev/xvdf"
DATA_MOUNT="/data"

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
log "Mounting data volume $DATA_DISK -> $DATA_MOUNT..."
if ! blkid "$DATA_DISK" &>/dev/null; then
  mkfs.ext4 -F "$DATA_DISK"
fi
mkdir -p "$DATA_MOUNT"
mount "$DATA_DISK" "$DATA_MOUNT" || true
grep -q "$DATA_DISK" /etc/fstab || echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab

# ---- 3. OS 파라미터 조정 (OpenSearch 필수) ----
log "Tuning OS parameters for OpenSearch..."
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" >> /etc/sysctl.conf
echo "opensearch soft nofile 65536" >> /etc/security/limits.conf
echo "opensearch hard nofile 65536" >> /etc/security/limits.conf

# ---- 4. OpenSearch 설치 ----
log "Installing OpenSearch $OPENSEARCH_VERSION..."
curl -fsSL "https://artifacts.opensearch.org/releases/bundle/opensearch/${OPENSEARCH_VERSION}/opensearch-${OPENSEARCH_VERSION}-linux-x64.tar.gz" \
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
cluster.name: ${project_name}-search
node.name: node-1
path.data: $DATA_MOUNT/opensearch/data
path.logs: $DATA_MOUNT/opensearch/logs
network.host: 0.0.0.0
http.port: 9200
discovery.type: single-node
plugins.security.disabled: true
EOF

# -----------------------------------------------------------------------
# JVM heap 1500m 설정
# t3.medium(4GB)에서 안정적으로 운영하기 위한 핵심 설정입니다.
# 기본값(~4GB auto) 그대로 두면 OS 메모리가 고갈되어 OOM이 발생합니다.
# -----------------------------------------------------------------------
sed -i 's/-Xms[0-9]*[gGmM]/-Xms1500m/g' /opt/opensearch/config/jvm.options
sed -i 's/-Xmx[0-9]*[gGmM]/-Xmx1500m/g' /opt/opensearch/config/jvm.options

# jvm.options에 -Xms/-Xmx가 없을 경우 추가
grep -q "Xms" /opt/opensearch/config/jvm.options || echo "-Xms1500m" >> /opt/opensearch/config/jvm.options
grep -q "Xmx" /opt/opensearch/config/jvm.options || echo "-Xmx1500m" >> /opt/opensearch/config/jvm.options

# ---- 5. OpenSearch systemd 서비스 등록 ----
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

# 한국어 형태소 분석기 + KNN 플러그인 설치
/opt/opensearch/bin/opensearch-plugin install --batch analysis-nori || true
/opt/opensearch/bin/opensearch-plugin install --batch opensearch-knn || true
systemctl restart opensearch

# ---- 6. OpenSearch API 서비스 설치 ----
log "Installing OpenSearch API server..."
mkdir -p "$OPENSEARCH_API_DIR"
python3.11 -m venv "$OPENSEARCH_API_DIR/venv"

# [방법 A] S3에서 아카이브 다운로드 — GitHub Actions가 푸시한 아카이브를 pull
aws s3 cp "s3://$PROJECT_NAME-deploy/opensearch.tar.gz" /tmp/opensearch-api.tar.gz
tar -xzf /tmp/opensearch-api.tar.gz -C "$OPENSEARCH_API_DIR"

if [ -f "$OPENSEARCH_API_DIR/requirements.txt" ]; then
  "$OPENSEARCH_API_DIR/venv/bin/pip" install -q -r "$OPENSEARCH_API_DIR/requirements.txt"
fi

chown -R ubuntu:ubuntu "$OPENSEARCH_API_DIR"

# ---- 7. OpenSearch API systemd 서비스 등록 ----
log "Registering opensearch-api systemd service..."
cat > /etc/systemd/system/opensearch-api.service <<'UNIT'
[Unit]
Description=OpenSearch API Server (ai-innovation)
Documentation=https://github.com/ai-innovation-challenge/opensearch
After=opensearch.service
Requires=opensearch.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/opensearch-api
Environment=OPENSEARCH_URL=http://localhost:9200
ExecStart=/opt/opensearch-api/venv/bin/uvicorn opensearch_api:app --host 0.0.0.0 --port 8010 --workers 2
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
systemctl start opensearch-api

log "OpenSearch server setup complete."
log "  OpenSearch:     systemctl status opensearch"
log "  OpenSearch API: systemctl status opensearch-api"
