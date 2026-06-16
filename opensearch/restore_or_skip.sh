#!/bin/bash
# OpenSearch S3 스냅샷 복원 스크립트 (재해 복구 전용)
#
# 운영 모델: OpenSearch는 DB(원본)에서 파생된 인덱스이자 라이브 저장소.
#   - 정상 운영: 보존 EBS(/data/opensearch)의 라이브 데이터를 그대로 사용 → 복원 스킵.
#     (라이브 등록분을 절대 덮어쓰지 않는다 — 과거: 고정 스냅샷 복원이 신규 등록분을 소실시킴)
#   - 재해 복구: EBS 유실 등으로 1차 인덱스가 비어있을 때만 S3의 "최신" 스냅샷에서 복원.
#     복원 후 누락분은 DB 기준 reconcile/재색인으로 보완한다.
set -euo pipefail

BUCKET="ai-innovation-deploy"
REGION="ap-northeast-2"
REPO_NAME="s3-backup"             # opensearch_setup.sh / 일일 cron과 동일한 repo (기존 s3_backup 불일치 수정)
BASE_PATH="opensearch-snapshots"
# 앱이 실제 검색에 사용하는 1차 인덱스. 레거시 product_index_v3가 아니라 멀티벡터 v4 기준으로 판단한다.
PRIMARY_INDEX="product_v4_combined"

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
echo "Registering S3 snapshot repository ($REPO_NAME)..."
curl -sf $CURL_TLS $CURL_AUTH -X PUT "$BASE_URL/_snapshot/$REPO_NAME" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"s3\",\"settings\":{\"bucket\":\"$BUCKET\",\"base_path\":\"$BASE_PATH\",\"region\":\"$REGION\"}}"
echo ""

# 1차 인덱스에 데이터가 있으면 = 보존 EBS 정상 → 복원 스킵 (라이브 데이터 보호)
COUNT=$(curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/$PRIMARY_INDEX/_count" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', 0))" 2>/dev/null \
  || echo 0)

echo "$PRIMARY_INDEX 현재 문서 수: $COUNT"

if [ "$COUNT" -gt "0" ]; then
  echo "라이브 데이터가 존재합니다 (보존 EBS 정상). 복원 스킵."
  exit 0
fi

echo "1차 인덱스가 비어있습니다 (EBS 유실 추정). S3 최신 스냅샷 확인 중..."

# repo의 스냅샷 중 state=SUCCESS이며 start_time이 가장 최근인 것을 선택.
# (과거: 고정 이름 opensearch_snapshot만 복원 → 일일 cron 스냅샷을 무시하고 옛 시점으로 회귀)
LATEST_SNAPSHOT=$(curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/_snapshot/$REPO_NAME/_all" 2>/dev/null \
  | python3 -c "
import sys, json
try:
    snaps = json.load(sys.stdin).get('snapshots', [])
except Exception:
    snaps = []
ok = [s for s in snaps if s.get('state') == 'SUCCESS']
ok.sort(key=lambda s: s.get('start_time_in_millis', 0))
print(ok[-1]['snapshot'] if ok else '')
" 2>/dev/null || echo "")

if [ -z "$LATEST_SNAPSHOT" ]; then
  echo "복원 가능한 스냅샷이 없습니다. DB 기준 재색인이 필요합니다."
  exit 0
fi

echo "최신 스냅샷 복원 시작: $LATEST_SNAPSHOT"

# 1차 인덱스가 비어있는 재해 복구 상황이므로 기존 product 인덱스를 정리한 뒤 복원한다.
# (정상 운영 경로는 위 COUNT>0 가드에서 이미 종료되므로 라이브 데이터는 여기 도달하지 않는다)
curl -s $CURL_TLS $CURL_AUTH -X DELETE "$BASE_URL/product_*" || true
sleep 2

# 스냅샷 복원 (글로벌 상태 제외, product 인덱스만)
curl -sf $CURL_TLS $CURL_AUTH -X POST \
  "$BASE_URL/_snapshot/$REPO_NAME/$LATEST_SNAPSHOT/_restore?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d '{"indices": "product_*", "ignore_unavailable": true, "include_global_state": false}'

echo ""
echo "스냅샷 복원 완료. (복원 후 DB와의 차이는 reconcile/재색인으로 보완)"
curl -s $CURL_TLS $CURL_AUTH "$BASE_URL/_cat/indices?h=index,docs.count,health" | grep product
