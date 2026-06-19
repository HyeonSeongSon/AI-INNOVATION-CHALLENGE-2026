#!/bin/bash
# OpenSearch S3 스냅샷 생성 스크립트
# 인덱싱 완료 후 수동으로 실행 (GitHub Actions snapshot.yml 워크플로우 사용)
set -euo pipefail

BUCKET="ai-innovation-deploy"
REGION="ap-northeast-2"
REPO_NAME="s3-backup"             # restore_or_skip.sh / opensearch_setup.sh 일일 cron과 동일 repo로 통일
SNAPSHOT_NAME="opensearch_snapshot"

# /etc/opensearch-admin.env 에서 관리자 패스워드 추출 (opensearch_setup.sh가 작성) —
# opensearch-api가 별도 EC2로 분리되어 이 인스턴스에는 opensearch-api.service가 없음
OS_PASSWORD=$(grep -Po 'OPENSEARCH_ADMIN_PASSWORD=\K[^ \n]+' \
  /etc/opensearch-admin.env 2>/dev/null | head -1 || true)
if [ -z "$OS_PASSWORD" ]; then
  echo "ERROR: OPENSEARCH_ADMIN_PASSWORD를 /etc/opensearch-admin.env에서 찾을 수 없습니다."
  exit 1
fi

BASE_URL="https://localhost:9200"
CURL_AUTH="-u admin:$OS_PASSWORD"
CURL_TLS="-k"

# S3 스냅샷 repository 등록
echo "Registering S3 snapshot repository..."
curl -sf $CURL_TLS $CURL_AUTH -X PUT "$BASE_URL/_snapshot/$REPO_NAME" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"s3\",\"settings\":{\"bucket\":\"$BUCKET\",\"base_path\":\"opensearch-snapshots\",\"region\":\"$REGION\"}}"
echo ""

# 인덱스 상태 확인
echo "현재 인덱스 상태:"
curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/_cat/indices?h=index,docs.count,health" | grep product

# 기존 스냅샷 삭제
echo "기존 스냅샷 삭제 중..."
curl -s $CURL_TLS $CURL_AUTH -X DELETE "$BASE_URL/_snapshot/$REPO_NAME/$SNAPSHOT_NAME" || true
sleep 3

# 새 스냅샷 생성 (전체 product 인덱스 포함, 완료까지 대기)
echo "스냅샷 생성 중: $SNAPSHOT_NAME (수 분 소요)"
curl -sf $CURL_TLS $CURL_AUTH -X PUT \
  "$BASE_URL/_snapshot/$REPO_NAME/$SNAPSHOT_NAME?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d '{"indices": "product_*", "ignore_unavailable": true, "include_global_state": false}'

echo ""
echo "스냅샷 생성 완료: s3://$BUCKET/opensearch-snapshots/"
