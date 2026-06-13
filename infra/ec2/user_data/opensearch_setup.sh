#!/bin/bash
# OpenSearch EC2 설치 스크립트
# opensearch_server.sh (user_data 부트스트랩)이 S3에서 내려받아 실행한다.
# 환경변수는 부트스트랩에서 export된 값을 사용한다:
#   PROJECT_NAME, OPENSEARCH_VERSION, INTERNAL_TOKEN, OPENSEARCH_ADMIN_PASSWORD
#
# 메모리 예산 (t3.medium 4GB):
#   OpenSearch JVM heap: 1000m (실사용 ~1200MB)
#   opensearch-api + KURE-v1: ~1500MB
#   OS + SSM: ~600MB
#   여유: 스왑 4GB로 보완
# 주의: JVM 1500m 이상 시 KURE-v1 로드 후 SSM 에이전트 OOM으로 배포 불가
set -euo pipefail

OPENSEARCH_API_DIR="/opt/opensearch-api"
DATA_MOUNT="/data"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }

# ---- 1. 시스템 업데이트 ----
log "Waiting for apt lock..."
# Ubuntu 최초 부팅 시 unattended-upgrades가 dpkg lock 점유 — 해제까지 대기
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
apt-get upgrade -y -qq
apt-get install -y -qq gnupg openjdk-17-jdk python3.11 python3.11-venv python3-pip git

# ---- 2. EBS 데이터 볼륨 마운트 ----
log "Waiting for EBS data volume..."
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
log "Mounting $DATA_DISK -> $DATA_MOUNT..."
if ! blkid "$DATA_DISK" &>/dev/null; then
  mkfs.ext4 -F "$DATA_DISK"
fi
mkdir -p "$DATA_MOUNT"
mount "$DATA_DISK" "$DATA_MOUNT" || true
grep -q "$DATA_DISK" /etc/fstab || echo "$DATA_DISK $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab

# ---- 3. 스왑 파일 ----
log "Setting up 4GB swap..."
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
fi
swapon /swapfile 2>/dev/null || true
grep -q swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab

# ---- 4. OS 파라미터 ----
log "Tuning OS parameters..."
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" >> /etc/sysctl.conf
echo "opensearch soft nofile 65536" >> /etc/security/limits.conf
echo "opensearch hard nofile 65536" >> /etc/security/limits.conf

# ---- 5. OpenSearch 설치 ----
log "Downloading OpenSearch $OPENSEARCH_VERSION..."
S3_KEY="opensearch-$OPENSEARCH_VERSION-linux-x64.tar.gz"
# S3 Gateway Endpoint 경유 (NAT 우회, 무료)
DOWNLOADED=false
for i in $(seq 1 20); do
  if /usr/local/bin/aws s3 cp "s3://$PROJECT_NAME-deploy/$S3_KEY" /tmp/opensearch.tar.gz 2>/dev/null; then
    log "Downloaded from S3 (attempt $i)."
    DOWNLOADED=true
    break
  fi
  log "S3 tarball not ready ($i/20), waiting 30s..."
  sleep 30
done
if [ "$DOWNLOADED" = "false" ]; then
  log "Falling back to direct download..."
  curl -fsSL \
    "https://artifacts.opensearch.org/releases/bundle/opensearch/$OPENSEARCH_VERSION/opensearch-$OPENSEARCH_VERSION-linux-x64.tar.gz" \
    -o /tmp/opensearch.tar.gz
fi
mkdir -p /opt/opensearch
tar xzf /tmp/opensearch.tar.gz -C /opt/opensearch --strip-components=1
rm /tmp/opensearch.tar.gz

mkdir -p "$DATA_MOUNT/opensearch/data" "$DATA_MOUNT/opensearch/logs"
useradd -r -s /bin/false opensearch 2>/dev/null || true
chown -R opensearch:opensearch /opt/opensearch "$DATA_MOUNT/opensearch"

# ---- TLS 인증서 생성 ----
log "Generating TLS certificates..."
mkdir -p /opt/opensearch/config/certs
(
  cd /opt/opensearch/config/certs
  openssl genrsa -out root-ca-key.pem 2048
  openssl req -new -x509 -sha256 -key root-ca-key.pem -out root-ca.pem -days 3650 \
    -subj "/C=KR/O=ai-innovation/CN=opensearch-root-ca"
  openssl genrsa -out node-key.pem 2048
  openssl req -new -key node-key.pem -out node.csr \
    -subj "/C=KR/O=ai-innovation/CN=opensearch-node-1"
  openssl x509 -req -in node.csr -CA root-ca.pem -CAkey root-ca-key.pem \
    -CAcreateserial -out node.pem -days 3650 -sha256
  openssl genrsa -out admin-key.pem 2048
  openssl req -new -key admin-key.pem -out admin.csr \
    -subj "/C=KR/O=ai-innovation/CN=opensearch-admin"
  openssl x509 -req -in admin.csr -CA root-ca.pem -CAkey root-ca-key.pem \
    -CAcreateserial -out admin.pem -days 3650 -sha256
)
chown -R opensearch:opensearch /opt/opensearch/config/certs
chmod 600 /opt/opensearch/config/certs/*-key.pem

# opensearch.yml
cat > /opt/opensearch/config/opensearch.yml <<EOF
cluster.name: $PROJECT_NAME-search
node.name: node-1
path.data: $DATA_MOUNT/opensearch/data
path.logs: $DATA_MOUNT/opensearch/logs
network.host: 0.0.0.0
http.port: 9200
discovery.type: single-node
plugins.security.ssl.transport.pemcert_filepath: certs/node.pem
plugins.security.ssl.transport.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.transport.enforce_hostname_verification: false
plugins.security.ssl.http.enabled: true
plugins.security.ssl.http.pemcert_filepath: certs/node.pem
plugins.security.ssl.http.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.allow_unsafe_democertificates: false
plugins.security.allow_default_init_securityindex: true
plugins.security.authcz.admin_dn:
  - "CN=opensearch-admin,O=ai-innovation,C=KR"
plugins.security.nodes_dn:
  - "CN=opensearch-node-1,O=ai-innovation,C=KR"
EOF

# JVM heap 1000m — 반드시 1000m 이하 유지 (SSM 에이전트 OOM 방지)
sed -i 's/-Xms[0-9]*[gGmM]/-Xms1000m/g' /opt/opensearch/config/jvm.options
sed -i 's/-Xmx[0-9]*[gGmM]/-Xmx1000m/g' /opt/opensearch/config/jvm.options
grep -q "Xms" /opt/opensearch/config/jvm.options || echo "-Xms1000m" >> /opt/opensearch/config/jvm.options
grep -q "Xmx" /opt/opensearch/config/jvm.options || echo "-Xmx1000m" >> /opt/opensearch/config/jvm.options

# ---- 6. OpenSearch systemd 서비스 ----
log "Registering opensearch service..."
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

# OpenSearch 기동 대기 (최대 300초 — t3.medium JVM 콜드 스타트 60~150초)
log "Waiting for OpenSearch to be ready..."
OS_READY=false
for i in $(seq 1 60); do
  if curl -sk https://localhost:9200/_cluster/health \
       -u "admin:$OPENSEARCH_ADMIN_PASSWORD" &>/dev/null; then
    log "OpenSearch is ready (attempt $i)."
    OS_READY=true
    break
  fi
  sleep 5
done
if [ "$OS_READY" = "false" ]; then
  log "ERROR: OpenSearch did not start within 300 seconds."
  exit 1
fi

# ---- 보안 플러그인 초기화 ----
log "Initializing OpenSearch security..."
HASHED_PW=$(/opt/opensearch/plugins/opensearch-security/tools/hash.sh \
  -p "$OPENSEARCH_ADMIN_PASSWORD" | tail -1)
INTERNAL_USERS="/opt/opensearch/config/opensearch-security/internal_users.yml"
sed -i "s|hash: \".*\"|hash: \"$HASHED_PW\"|g" "$INTERNAL_USERS"

# securityadmin.sh: 최대 5회 재시도 (OpenSearch 완전 준비 후에도 일시적 거부 가능)
SEC_OK=false
for i in $(seq 1 5); do
  if /opt/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
      -cd /opt/opensearch/config/opensearch-security/ \
      -icl -nhnv \
      -cacert /opt/opensearch/config/certs/root-ca.pem \
      -cert   /opt/opensearch/config/certs/admin.pem \
      -key    /opt/opensearch/config/certs/admin-key.pem \
      -h localhost; then
    log "Security initialized (attempt $i)."
    SEC_OK=true
    break
  fi
  log "securityadmin.sh failed, retrying in 30s... ($i/5)"
  sleep 30
done
if [ "$SEC_OK" = "false" ]; then
  log "ERROR: Failed to initialize OpenSearch security after 5 attempts."
  exit 1
fi

# ---- 플러그인 설치 ----
PLUGIN_LIST=$(/opt/opensearch/bin/opensearch-plugin list 2>/dev/null || echo "")
PLUGINS_CHANGED=false
for PLUGIN in analysis-nori opensearch-knn repository-s3; do
  if echo "$PLUGIN_LIST" | grep -q "$PLUGIN"; then
    log "Plugin $PLUGIN already installed, skipping."
  else
    /opt/opensearch/bin/opensearch-plugin install --batch "$PLUGIN" || true
    PLUGINS_CHANGED=true
  fi
done
if [ "$PLUGINS_CHANGED" = "true" ]; then
  systemctl restart opensearch
fi

# ---- 7. OpenSearch API venv ----
log "Setting up OpenSearch API venv..."
mkdir -p "$OPENSEARCH_API_DIR"
# EBS(/data)에 venv 보존 — EC2 재생성 후에도 재설치 스킵 (~450MB 절감)
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
chown -R ubuntu:ubuntu "$OPENSEARCH_API_DIR" "$DATA_MOUNT/opensearch-api-venv"

# ---- 8. OpenSearch API systemd 서비스 ----
log "Registering opensearch-api service..."
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
Environment=OPENSEARCH_URL=https://localhost:9200
Environment=OPENSEARCH_HOST=localhost
Environment=OPENSEARCH_PORT=9200
Environment=OPENSEARCH_USE_SSL=true
Environment=OPENSEARCH_ADMIN_PASSWORD=$OPENSEARCH_ADMIN_PASSWORD
Environment=INTERNAL_TOKEN=$INTERNAL_TOKEN
Environment=FORBIDDEN_KEYWORD_JSON_PATH=/opt/opensearch-api/data/forbidden_keyword.json
ExecStartPre=/bin/sleep 60
ExecStart=$DATA_MOUNT/opensearch-api-venv/bin/uvicorn opensearch_api:app --host 0.0.0.0 --port 8010 --workers 1
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

log "OpenSearch setup complete."
touch /var/log/user-data-complete
