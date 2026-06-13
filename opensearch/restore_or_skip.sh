#!/bin/bash
# OpenSearch S3 스냅샷 복원 스크립트
# 인덱스가 비어있으면 S3 스냅샷에서 복원, 이미 있으면 스킵
set -euo pipefail

BUCKET="ai-innovation-deploy"
REGION="ap-northeast-2"
REPO_NAME="s3_backup"
SNAPSHOT_NAME="opensearch_snapshot"

# opensearch-api.service 에서 관리자 패스워드 추출
# SSM 실행 환경에는 OPENSEARCH_ADMIN_PASSWORD가 없으므로 서비스 파일에서 읽음
OS_PASSWORD=$(grep -Po 'OPENSEARCH_ADMIN_PASSWORD=\K[^ \n]+' \
  /etc/systemd/system/opensearch-api.service 2>/dev/null | head -1 || true)
if [ -z "$OS_PASSWORD" ]; then
  echo "ERROR: OPENSEARCH_ADMIN_PASSWORD를 서비스 파일에서 찾을 수 없습니다."
  exit 1
fi

# OpenSearch는 TLS가 활성화된 HTTPS 전용 — -k로 자체 서명 인증서 허용
BASE_URL="https://localhost:9200"
CURL_AUTH="-u admin:$OS_PASSWORD"
CURL_TLS="-k"

# S3 스냅샷 repository 등록 (멱등 — 매번 실행해도 안전)
echo "Registering S3 snapshot repository..."
curl -sf $CURL_TLS $CURL_AUTH -X PUT "$BASE_URL/_snapshot/$REPO_NAME" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"s3\",\"settings\":{\"bucket\":\"$BUCKET\",\"base_path\":\"opensearch-snapshots\",\"region\":\"$REGION\"}}"
echo ""

# 인덱스에 데이터가 있는지 확인
COUNT=$(curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/product_index_v3/_count" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', 0))" 2>/dev/null \
  || echo 0)

echo "product_index_v3 현재 문서 수: $COUNT"

if [ "$COUNT" -gt "100" ]; then
  echo "인덱스에 데이터가 있습니다. 복원 스킵."
  exit 0
fi

echo "인덱스가 비어있습니다. S3 스냅샷 확인 중..."

# S3 스냅샷 존재 여부 확인
SNAP_COUNT=$(curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/_snapshot/$REPO_NAME/$SNAPSHOT_NAME" 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('snapshots', [])))" 2>/dev/null \
  || echo 0)

if [ "$SNAP_COUNT" -eq "0" ]; then
  echo "S3 스냅샷이 없습니다. 수동 인덱싱이 필요합니다."
  exit 0
fi

echo "S3 스냅샷 복원 시작: $SNAPSHOT_NAME"

# 기존 product 인덱스 삭제 (복원 전 클린업)
curl -s $CURL_TLS $CURL_AUTH -X DELETE "$BASE_URL/product_*" || true
sleep 2

# 스냅샷 복원 (글로벌 상태 제외, product 인덱스만)
curl -sf $CURL_TLS $CURL_AUTH -X POST \
  "$BASE_URL/_snapshot/$REPO_NAME/$SNAPSHOT_NAME/_restore?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d '{"ignore_unavailable": true, "include_global_state": false}'

echo ""
echo "스냅샷 복원 완료."
curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/_cat/indices?h=index,docs.count,health" | grep product
