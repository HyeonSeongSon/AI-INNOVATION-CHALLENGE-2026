#!/usr/bin/env bash
# 22차 부하테스트 — OpenSearch는 AWS 관리형 서비스가 아니라 EC2 자체 호스팅이라
# AWS/OpenSearch CloudWatch 네임스페이스(JVMMemoryPressure 등)가 존재하지 않는다.
# 대신 노드 자체의 _nodes/stats API를 SSM으로 직접 호출해 JVM/스레드풀 상태를 스냅샷한다.
#
# 비밀번호는 절대 이 스크립트나 SSM 명령 파라미터에 평문으로 넣지 않는다 —
# 인스턴스에 이미 올라가 있는 OPENSEARCH_ADMIN_PASSWORD 환경변수를 인스턴스 쪽에서 그대로 사용한다.
#
# 사용법: ./fetch_opensearch_node_stats.sh <before|after> <output_dir>

set -euo pipefail

LABEL="${1:?before 또는 after}"
OUTPUT_DIR="${2:?출력 디렉터리}"
OPENSEARCH_INSTANCE_ID="${OPENSEARCH_INSTANCE_ID:-i-0603d62e9349ea0a9}"
REGION="${REGION:-ap-northeast-2}"

mkdir -p "$OUTPUT_DIR"

COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$OPENSEARCH_INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "loadtest-22-opensearch-node-stats-${LABEL}" \
  --parameters 'commands=["PASS=$(grep -m1 OPENSEARCH_ADMIN_PASSWORD /proc/$(pgrep -f opensearch | head -1)/environ 2>/dev/null | cut -d= -f2- | tr -d \"\\0\"); curl -s -k -u admin:$PASS https://localhost:9200/_nodes/stats/jvm,thread_pool"]' \
  --region "$REGION" \
  --query 'Command.CommandId' --output text)

sleep 5

aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$OPENSEARCH_INSTANCE_ID" \
  --region "$REGION" \
  --query 'StandardOutputContent' --output text > "${OUTPUT_DIR}/opensearch_nodes_stats_${LABEL}.json"

echo "저장 완료: ${OUTPUT_DIR}/opensearch_nodes_stats_${LABEL}.json"
