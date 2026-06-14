#!/bin/bash
# Bootstrap: AWS CLI 설치 후 S3에서 실제 설치 스크립트를 내려받아 실행한다.
# 크기 제한: EC2 user_data는 base64 인코딩 후 16KB 이하 — 이 파일은 부트스트랩만 담는다.
# 실제 설치 로직: infra/ec2/user_data/opensearch_setup.sh (S3 경유 배포)
#
# setup.sh는 내용 해시로 버전 키화된다: s3://.../opensearch_setup.<setup_hash>.sh
#   - CI가 sha256으로 해시를 계산해 S3 업로드 + Terraform var로 주입
#   - 이 부트스트랩이 해시 키만 받으므로 이전 배포의 낡은 setup.sh를 받는 race가 없다
#   - setup.sh가 바뀌면 해시→user_data 변경→EC2 자동 교체 (수동 리비전 관리 불필요)
SETUP_HASH="${setup_hash}"
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

# 해시 키 setup.sh를 S3에서 대기 (terraform apply 전 CI가 업로드, 최대 20분)
SETUP_KEY="opensearch_setup.$SETUP_HASH.sh"
log "Bootstrap: waiting for $SETUP_KEY in S3..."
SETUP_READY=false
for i in $(seq 1 20); do
  if /usr/local/bin/aws s3 cp \
      "s3://$PROJECT_NAME-deploy/$SETUP_KEY" \
      /tmp/opensearch_setup.sh 2>/dev/null; then
    log "Bootstrap: setup script downloaded (attempt $i)."
    SETUP_READY=true
    break
  fi
  log "Bootstrap: not ready yet ($i/20), waiting 60s..."
  sleep 60
done

if [ "$SETUP_READY" = "false" ]; then
  log "ERROR: $SETUP_KEY not found in S3 after 20 minutes."
  exit 1
fi

chmod +x /tmp/opensearch_setup.sh
log "Bootstrap: executing opensearch_setup.sh..."
exec bash /tmp/opensearch_setup.sh
