#!/bin/bash
# Bootstrap: AWS CLI 설치 후 S3에서 실제 설치 스크립트를 내려받아 실행한다.
# 크기 제한: EC2 user_data는 base64 인코딩 후 16KB 이하 — 이 파일은 부트스트랩만 담는다.
# 실제 설치 로직: infra/ec2/user_data/opensearch_setup.sh (S3 경유 배포)
#
# SETUP_REVISION: opensearch_setup.sh 를 수정할 때마다 이 숫자를 올린다.
#   user_data(=이 부트스트랩) 내용이 바뀌어야 user_data_replace_on_change=true 가
#   EC2를 교체하고 새 setup.sh 를 실제로 실행한다. setup.sh 만 고치면 반영되지 않는다.
# SETUP_REVISION: 2
set -euo pipefail

# Terraform templatefile 변수 → 쉘 환경변수로 export (setup.sh에서 사용)
export PROJECT_NAME="${project_name}"
export OPENSEARCH_VERSION="${OPENSEARCH_VERSION}"
export INTERNAL_TOKEN="${internal_token}"
export OPENSEARCH_ADMIN_PASSWORD="${opensearch_admin_password}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/user-data.log; }

log "Bootstrap: installing curl + unzip + AWS CLI..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl unzip

curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws
log "Bootstrap: AWS CLI installed."

# package-data-services job이 opensearch_setup.sh를 S3에 올릴 때까지 대기 (최대 20분)
log "Bootstrap: waiting for opensearch_setup.sh in S3..."
SETUP_READY=false
for i in $(seq 1 20); do
  if /usr/local/bin/aws s3 cp \
      "s3://$PROJECT_NAME-deploy/opensearch_setup.sh" \
      /tmp/opensearch_setup.sh 2>/dev/null; then
    log "Bootstrap: setup script downloaded (attempt $i)."
    SETUP_READY=true
    break
  fi
  log "Bootstrap: not ready yet ($i/20), waiting 60s..."
  sleep 60
done

if [ "$SETUP_READY" = "false" ]; then
  log "ERROR: opensearch_setup.sh not found in S3 after 20 minutes."
  exit 1
fi

chmod +x /tmp/opensearch_setup.sh
log "Bootstrap: executing opensearch_setup.sh..."
exec bash /tmp/opensearch_setup.sh
