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
log "Waiting for cloud-init apt lock to release..."
# Ubuntu 최초 부팅 시 unattended-upgrades가 dpkg lock을 점유 — 해제까지 대기
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
S3_KEY="opensearch-$OPENSEARCH_VERSION-linux-x64.tar.gz"
# S3 Gateway Endpoint 경유 (NAT 우회, 무료) — package-data-services job이 먼저 캐시
# 최대 10분 대기 후 fallback
DOWNLOADED=false
for i in $(seq 1 20); do
  if /usr/local/bin/aws s3 cp "s3://$PROJECT_NAME-deploy/$S3_KEY" /tmp/opensearch.tar.gz 2>/dev/null; then
    log "Downloaded OpenSearch from S3 (attempt $i)."
    DOWNLOADED=true
    break
  fi
  log "S3 tarball not ready yet, waiting 30s... ($i/20)"
  sleep 30
done
if [ "$DOWNLOADED" = "false" ]; then
  log "S3 unavailable, falling back to direct download..."
  curl -fsSL \
    "https://artifacts.opensearch.org/releases/bundle/opensearch/$${OPENSEARCH_VERSION}/opensearch-$${OPENSEARCH_VERSION}-linux-x64.tar.gz" \
    -o /tmp/opensearch.tar.gz
fi
mkdir -p /opt/opensearch
tar xzf /tmp/opensearch.tar.gz -C /opt/opensearch --strip-components=1
rm /tmp/opensearch.tar.gz

# 데이터/로그를 EBS 볼륨으로 설정
mkdir -p "$DATA_MOUNT/opensearch/data" "$DATA_MOUNT/opensearch/logs"
useradd -r -s /bin/false opensearch 2>/dev/null || true
chown -R opensearch:opensearch /opt/opensearch "$DATA_MOUNT/opensearch"

# ---- TLS 인증서 생성 (root CA → node cert → admin cert) ----
log "Generating TLS certificates for OpenSearch security..."
mkdir -p /opt/opensearch/config/certs
(
  cd /opt/opensearch/config/certs
  # Root CA
  openssl genrsa -out root-ca-key.pem 2048
  openssl req -new -x509 -sha256 -key root-ca-key.pem -out root-ca.pem -days 3650 \
    -subj "/C=KR/O=ai-innovation/CN=opensearch-root-ca"
  # Node cert (HTTP + transport 겸용)
  openssl genrsa -out node-key.pem 2048
  openssl req -new -key node-key.pem -out node.csr \
    -subj "/C=KR/O=ai-innovation/CN=opensearch-node-1"
  openssl x509 -req -in node.csr -CA root-ca.pem -CAkey root-ca-key.pem \
    -CAcreateserial -out node.pem -days 3650 -sha256
  # Admin cert (securityadmin.sh 전용)
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
# TLS — transport layer
plugins.security.ssl.transport.pemcert_filepath: certs/node.pem
plugins.security.ssl.transport.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.transport.enforce_hostname_verification: false
# TLS — HTTP layer
plugins.security.ssl.http.enabled: true
plugins.security.ssl.http.pemcert_filepath: certs/node.pem
plugins.security.ssl.http.pemkey_filepath: certs/node-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: certs/root-ca.pem
# Security plugin
plugins.security.allow_unsafe_democertificates: false
plugins.security.allow_default_init_securityindex: true
plugins.security.authcz.admin_dn:
  - "CN=opensearch-admin,O=ai-innovation,C=KR"
plugins.security.nodes_dn:
  - "CN=opensearch-node-1,O=ai-innovation,C=KR"
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

# OpenSearch 준비 대기 (최대 300초)
# t3.medium에서 JVM 콜드 스타트는 60~150초 소요 — 120초 상한은 부족
log "Waiting for OpenSearch to be ready..."
OS_READY=false
for i in $(seq 1 60); do
  if curl -sk https://localhost:9200/_cluster/health \
       -u "admin:${opensearch_admin_password}" &>/dev/null; then
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
log "Initializing OpenSearch security plugin..."
HASHED_PW=$(/opt/opensearch/plugins/opensearch-security/tools/hash.sh \
  -p "${opensearch_admin_password}" | tail -1)
INTERNAL_USERS="/opt/opensearch/config/opensearch-security/internal_users.yml"
sed -i "s|hash: \".*\"|hash: \"$HASHED_PW\"|g" "$INTERNAL_USERS"
# securityadmin.sh: OpenSearch가 완전히 준비된 직후에도 일시적으로 거부할 수 있음 — 최대 5회 재시도
SEC_OK=false
for i in $(seq 1 5); do
  if /opt/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
      -cd /opt/opensearch/config/opensearch-security/ \
      -icl -nhnv \
      -cacert /opt/opensearch/config/certs/root-ca.pem \
      -cert  /opt/opensearch/config/certs/admin.pem \
      -key   /opt/opensearch/config/certs/admin-key.pem \
      -h localhost; then
    log "OpenSearch security initialized (attempt $i)."
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

# 플러그인 설치: 한국어 형태소 분석기 + KNN + S3 스냅샷
# 이미 설치된 플러그인은 스킵 — EC2 재생성 시 매번 재설치되나, 동일 인스턴스 재실행 방어
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

# ---- 7. OpenSearch API 서비스 설치 ----
log "Installing OpenSearch API server..."
mkdir -p "$OPENSEARCH_API_DIR"
# venv는 EBS(/data)에 생성 — EC2 재생성(루트 디스크 초기화) 후에도 EBS는 보존됨
# torch(~300MB) + transformers(~150MB) 재다운로드 방지
if [ -f "$DATA_MOUNT/opensearch-api-venv/bin/python" ]; then
  log "EBS venv already exists, skipping torch/transformers install."
else
  log "Creating venv and installing torch + transformers..."
  python3.11 -m venv "$DATA_MOUNT/opensearch-api-venv"
  # CPU-only torch: CUDA 2GB 다운로드 방지
  # transformers==4.41.0: 5.x에서 sentence-transformers와 torch._dynamo 충돌
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q --upgrade pip
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
  "$DATA_MOUNT/opensearch-api-venv/bin/pip" install -q "transformers==4.41.0"
fi
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
Environment=OPENSEARCH_URL=https://localhost:9200
Environment=OPENSEARCH_HOST=localhost
Environment=OPENSEARCH_PORT=9200
Environment=OPENSEARCH_USE_SSL=true
Environment=OPENSEARCH_ADMIN_PASSWORD=${opensearch_admin_password}
Environment=INTERNAL_TOKEN=$INTERNAL_TOKEN
Environment=FORBIDDEN_KEYWORD_JSON_PATH=/opt/opensearch-api/data/forbidden_keyword.json
# OpenSearch 완전 기동 후 60초 추가 대기
# — 재부팅 직후 SSM 에이전트가 메모리를 확보할 시간을 확보합니다
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
# 코드는 GitHub Actions SSM 배포에서 설치 후 시작

log "OpenSearch server setup complete."
log "  OpenSearch:     systemctl status opensearch"
log "  OpenSearch API: systemctl status opensearch-api"
touch /var/log/user-data-complete
