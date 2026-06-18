#!/usr/bin/env bash
# 22차 부하테스트 — /chat/v2/stream 동시성 게이팅 검증.
# loadtest EC2(VPC 내부)에서 실행한다. 로컬 머신에서 직접 실행하지 말 것
# (curl 동시 220+에서 클라이언트 자체가 깨지는 현상 확인됨).
#
# 로그인은 CloudFront(HTTPS)로, 실제 부하(채팅 호출)는 ALB(HTTP) 직접으로 나눈다 —
# access_token 쿠키가 Secure 속성을 가지므로 HTTP로 로그인하면 curl이 저장을 거부하고,
# CloudFront의 OriginReadTimeout(60s)은 graph_execution_timeout(600s)보다 짧아 ALB를
# 거치지 않고 직접 호출해야 한다. 쿠키 도메인도 두 호스트가 달라 자동 매칭이 안 되므로
# 로그인 후 access_token 값만 추출해 Cookie 헤더로 직접 첨부한다
# (verification-results.md 1856/1970행, 16차/이후 검증에서 확립된 방식).
#
# 필수 환경변수:
#   CF_HOST        예) d2x7wd8p914cyl.cloudfront.net (로그인용, HTTPS)
#   ALB_HOST       예) ai-innovation-alb-105766867.ap-northeast-2.elb.amazonaws.com (부하용, HTTP)
#   TEST_PASSWORD  loadtest001~100@example.com 공용 임시 비밀번호 (SSM 파라미터에 평문 노출 금지 —
#                  호출자가 Secrets Manager에서 받아 환경변수로만 주입)
#
# 선택 환경변수:
#   CONCURRENCY        기본 100
#   LOGIN_BATCH_SIZE    기본 8   (rate_limit_login_max_requests=10/60s 대비 여유)
#   LOGIN_BATCH_SLEEP   기본 65  (rate_limit_login_window_seconds=60 대비 여유)
#   CURL_TIMEOUT        기본 700 (graph_execution_timeout=600 + ALB idle_timeout=660 대비 여유)

set -euo pipefail

: "${CF_HOST:?CF_HOST 환경변수가 필요합니다}"
: "${ALB_HOST:?ALB_HOST 환경변수가 필요합니다}"
: "${TEST_PASSWORD:?TEST_PASSWORD 환경변수가 필요합니다}"

CONCURRENCY="${CONCURRENCY:-100}"
LOGIN_BATCH_SIZE="${LOGIN_BATCH_SIZE:-8}"
LOGIN_BATCH_SLEEP="${LOGIN_BATCH_SLEEP:-65}"
CURL_TIMEOUT="${CURL_TIMEOUT:-700}"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT_DIR="$(dirname "$0")/results/${RUN_ID}"
COOKIE_DIR="${RESULT_DIR}/cookies"
SSE_DIR="${RESULT_DIR}/sse"
mkdir -p "$COOKIE_DIR" "$SSE_DIR"

echo "test_start=${RUN_ID}" > "${RESULT_DIR}/meta.env"
echo "cf_host=${CF_HOST}" >> "${RESULT_DIR}/meta.env"
echo "alb_host=${ALB_HOST}" >> "${RESULT_DIR}/meta.env"
echo "concurrency=${CONCURRENCY}" >> "${RESULT_DIR}/meta.env"

login_one() {
  local idx="$1"
  local email
  printf -v email 'loadtest%03d@example.com' "$idx"
  local cookie_file="${COOKIE_DIR}/${idx}.txt"
  local token_file="${COOKIE_DIR}/${idx}.token"

  local http_code
  http_code=$(curl -s -o /dev/null -w '%{http_code}' \
    -c "$cookie_file" \
    -X POST "https://${CF_HOST}/auth/login" \
    --data-urlencode "username=${email}" \
    --data-urlencode "password=${TEST_PASSWORD}")

  echo "${idx} ${email} login_http=${http_code}" >> "${RESULT_DIR}/login.log"

  if [ "$http_code" != "200" ]; then
    rm -f "$cookie_file"
    return 1
  fi

  # 쿠키 도메인이 CF_HOST라 ALB_HOST 호출에는 자동으로 안 붙는다 — 토큰 값만 추출해 따로 저장
  awk -F'\t' '$6 == "access_token" { print $7 }' "$cookie_file" > "$token_file"
  if [ ! -s "$token_file" ]; then
    rm -f "$cookie_file" "$token_file"
    return 1
  fi
}

echo "=== 로그인 단계: ${LOGIN_BATCH_SIZE}개씩 ${LOGIN_BATCH_SLEEP}s 간격 (rate limit 회피) ==="
idx=1
while [ "$idx" -le "$CONCURRENCY" ]; do
  batch_end=$((idx + LOGIN_BATCH_SIZE - 1))
  [ "$batch_end" -gt "$CONCURRENCY" ] && batch_end="$CONCURRENCY"

  for i in $(seq "$idx" "$batch_end"); do
    login_one "$i" &
  done
  wait

  idx=$((batch_end + 1))
  if [ "$idx" -le "$CONCURRENCY" ]; then
    sleep "$LOGIN_BATCH_SLEEP"
  fi
done

# 실패 계정 재시도 (1회) — 19차에서 효과 확인된 패턴
echo "=== 로그인 실패 계정 재시도 ==="
for i in $(seq 1 "$CONCURRENCY"); do
  if [ ! -s "${COOKIE_DIR}/${i}.token" ]; then
    sleep 1
    login_one "$i" || true
  fi
done

logged_in=$(find "$COOKIE_DIR" -name '*.token' -size +0c | wc -l)
echo "로그인 성공: ${logged_in}/${CONCURRENCY}"

echo "=== 부하 단계: 동시 ${CONCURRENCY}개 /chat/v2/stream 요청 (ALB 직접) ==="

# 계정마다 소유한 페르소나가 다르므로(소유권 검증으로 403 발생), 계정별 실제 소유 페르소나를
# persona_ids.txt(idx번째 줄 = idx번 계정이 소유한 페르소나)에서 읽어 사용한다.
PERSONA_FILE="$(dirname "$0")/persona_ids.txt"

send_one() {
  local idx="$1"
  local token_file="${COOKIE_DIR}/${idx}.token"
  [ -s "$token_file" ] || { echo "${idx} skip=no_token" >> "${RESULT_DIR}/send.log"; return; }
  local token
  token=$(cat "$token_file")
  local persona_id
  persona_id=$(sed -n "${idx}p" "$PERSONA_FILE")

  local body_file="${SSE_DIR}/${idx}.body.json"
  printf '{"user_input":"%s 에게 적합한 스킨케어 상품 추천 메시지 작성해줘","session_id":"loadtest22_%s"}' "$persona_id" "$idx" > "$body_file"

  local timing
  timing=$(curl -s -N -m "$CURL_TIMEOUT" \
    -H "Cookie: access_token=${token}" \
    -X POST "http://${ALB_HOST}/api/marketing/chat/v2/stream" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    --data-binary "@${body_file}" \
    -o "${SSE_DIR}/${idx}.sse.log" \
    -w '%{http_code} %{time_starttransfer} %{time_total}')

  echo "${idx} ${timing}" >> "${RESULT_DIR}/send.log"
}

export -f send_one
export COOKIE_DIR SSE_DIR RESULT_DIR ALB_HOST CURL_TIMEOUT PERSONA_FILE

seq 1 "$CONCURRENCY" | xargs -P "$CONCURRENCY" -I{} bash -c 'send_one "$@"' _ {}

echo "test_end=$(date -u +%Y%m%dT%H%M%SZ)" >> "${RESULT_DIR}/meta.env"
echo "=== 완료. 결과: ${RESULT_DIR} ==="
echo "${RESULT_DIR}"
