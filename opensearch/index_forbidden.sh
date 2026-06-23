#!/bin/bash
# forbidden_sentences 색인 one-shot (배포 SSM 단계에서 호출).
# opensearch-api.env(EnvironmentFile)에서 자격증명을 추출해 venv python으로 색인한다.
# index_forbidden_sentences.py는 count>0면 스킵하는 idempotent 구조.
# 인라인 SSM 명령의 작은따옴표 충돌을 피하려고 별도 스크립트로 분리 (restore_or_skip.sh와 동일 패턴).
set -eu

ENV_FILE=/etc/opensearch-api.env

OS_PW=$(grep -Po 'OPENSEARCH_ADMIN_PASSWORD=\K[^ ]+' "$ENV_FILE" | head -1)
if [ -z "$OS_PW" ]; then
  echo "ERROR: OPENSEARCH_ADMIN_PASSWORD를 환경변수 파일에서 찾을 수 없습니다."
  exit 1
fi

# opensearch-api는 OpenSearch 노드와 별도 EC2에서 돈다 — 호스트도 환경변수 파일에서 추출
# (opensearch_api_setup.sh가 OPENSEARCH_HOST를 OpenSearch 인스턴스의 private IP로 박아둔다)
OS_HOST=$(grep -Po 'OPENSEARCH_HOST=\K[^ ]+' "$ENV_FILE" | head -1)
if [ -z "$OS_HOST" ]; then
  echo "ERROR: OPENSEARCH_HOST를 환경변수 파일에서 찾을 수 없습니다."
  exit 1
fi

export OPENSEARCH_HOST="$OS_HOST"
export OPENSEARCH_PORT=9200
export OPENSEARCH_USE_SSL=true
export OPENSEARCH_ADMIN_PASSWORD="$OS_PW"
export FORBIDDEN_KEYWORD_JSON_PATH=/opt/opensearch-api/data/forbidden_keyword.json

cd /opt/opensearch-api
/data/opensearch-api-venv/bin/python index_forbidden_sentences.py
