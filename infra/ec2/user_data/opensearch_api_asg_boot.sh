#!/bin/bash
# ASG launch template user_data.
#
# 평소(골든 AMI로 부팅 — 코드/venv/모델/데이터가 이미 다 포함됨): 시크릿/피어 IP만 현재 값으로
# env 파일에 써주고 서비스를 재시작하는 가벼운 경로만 탄다.
#
# 콜드 폴백(아직 골든 AMI가 한 번도 구워지지 않아 launch template이 베이스 우분투 AMI를
# 가리키는 최초 상태): venv/코드가 없으므로 opensearch_api_setup.sh(무거운 설치)를 기존
# 단일 인스턴스와 동일한 S3 해시 버전 방식으로 받아 실행한다. 이 경로로 뜬 인스턴스는
# 코드(/opt/opensearch-api)가 비어 있을 수 있으므로 빌더로만 쓰고, 그 결과로 첫 골든 AMI를
# 만든 다음부터는 항상 평소 경로(env 갱신 + 재시작)만 타게 된다.
set -euo pipefail

DATA_MOUNT="/data"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }
trap 'log "FAILED at line $LINENO (exit $?)"' ERR

if [ ! -f "$DATA_MOUNT/opensearch-api-venv/bin/python" ]; then
  log "ASG boot: cold instance (no golden AMI baked yet) — running full heavy setup..."
  export PROJECT_NAME="${project_name}"
  export INTERNAL_TOKEN="${internal_token}"
  export OPENSEARCH_ADMIN_PASSWORD="${opensearch_admin_password}"
  export OPENSEARCH_HOST="${opensearch_host}"

  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl unzip
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install
  rm -rf /tmp/awscliv2.zip /tmp/aws

  SETUP_KEY="opensearch_api_setup.${setup_hash}.sh"
  log "ASG boot: waiting for $SETUP_KEY in S3..."
  SETUP_READY=false
  for i in $(seq 1 20); do
    if /usr/local/bin/aws s3 cp "s3://${project_name}-deploy/$SETUP_KEY" /tmp/opensearch_api_setup.sh 2>/dev/null; then
      SETUP_READY=true
      break
    fi
    sleep 60
  done
  if [ "$SETUP_READY" = "false" ]; then
    log "ERROR: $SETUP_KEY not found in S3 after 20 minutes."
    exit 1
  fi
  chmod +x /tmp/opensearch_api_setup.sh
  bash /tmp/opensearch_api_setup.sh
  log "ASG boot: cold setup complete (code/data still need a builder SSM deploy before this instance is usable)."
  exit 0
fi

log "ASG boot: golden AMI detected (venv present) — refreshing env file + restarting service..."
cat > /etc/opensearch-api.env <<ENVFILE
OPENSEARCH_URL=https://${opensearch_host}:9200
OPENSEARCH_HOST=${opensearch_host}
OPENSEARCH_PORT=9200
OPENSEARCH_USE_SSL=true
OPENSEARCH_ADMIN_PASSWORD=${opensearch_admin_password}
INTERNAL_TOKEN=${internal_token}
ENVFILE
chmod 600 /etc/opensearch-api.env
systemctl restart opensearch-api

log "ASG boot complete."
touch /var/log/user-data-complete
