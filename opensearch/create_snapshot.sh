#!/bin/bash
# OpenSearch S3 스냅샷 생성 스크립트
# 인덱싱 완료 후 수동으로 실행 (GitHub Actions snapshot.yml 워크플로우 사용)
set -euo pipefail

BUCKET="ai-innovation-deploy"
REGION="ap-northeast-2"
REPO_NAME="s3_backup"
SNAPSHOT_NAME="opensearch_snapshot"

# S3 스냅샷 repository 등록
echo "Registering S3 snapshot repository..."
curl -sf -X PUT "http://localhost:9200/_snapshot/$REPO_NAME" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"s3\",\"settings\":{\"bucket\":\"$BUCKET\",\"base_path\":\"opensearch-snapshots\",\"region\":\"$REGION\"}}"
echo ""

# 인덱스 상태 확인
echo "현재 인덱스 상태:"
curl -s "http://localhost:9200/_cat/indices?h=index,docs.count,health" | grep product

# 기존 스냅샷 삭제
echo "기존 스냅샷 삭제 중..."
curl -s -X DELETE "http://localhost:9200/_snapshot/$REPO_NAME/$SNAPSHOT_NAME" || true
sleep 3

# 새 스냅샷 생성 (전체 product 인덱스 포함, 완료까지 대기)
echo "스냅샷 생성 중: $SNAPSHOT_NAME (수 분 소요)"
curl -sf -X PUT \
  "http://localhost:9200/_snapshot/$REPO_NAME/$SNAPSHOT_NAME?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d '{"indices": "product_*", "ignore_unavailable": true, "include_global_state": false}'

echo ""
echo "스냅샷 생성 완료: s3://$BUCKET/opensearch-snapshots/"
