# QA Report: `/chat/v2/stream` 동시성 게이팅 검증

## 검증 상태
**완료 (코드 리뷰 기준 승인)** — backend-dev 게이팅 재작업 완료, 코드 리뷰로 검증. 실제 동시 요청을 이용한
부하/슬롯 점유 테스트는 로컬 Docker(Postgres/OpenSearch) 미가동으로 수행하지 못했으며, 원 플랜에서도
"부하/동시성 검증은 범위 제외"로 명시되어 있어 별도 부하테스트에서 확인 예정.

---

## 설계 변경 이력

1차 설계(폐기): plain `POST /chat/v2`가 즉시 `task_id`를 반환하고 `GET /chat/v2/jobs/{task_id}/stream`으로
진행 상황을 폴링하는 큐 구조. 코드 리뷰까지 진행했으나, **plain `/chat/v2`는 프론트엔드에서 호출되지 않는
죽은 코드**였던 것이 frontend-dev 검증 중 발견되어 폐기.

2차 설계(현재): 프론트엔드가 실제로 사용하는 `POST /chat/v2/stream`(astream_events 기반 SSE,
실시간 토큰 스트리밍 UX)에 동시성 게이팅(세마포어/큐)을 직접 추가. 엔드포인트·이벤트 계약 자체는
변경하지 않고, 동시 실행 그래프 수만 제한한다. 프론트엔드 변경 없음.

---

## 1차 설계 코드 리뷰에서 발견된 사항 (참고용 — 폐기된 설계)

- `create_job()`이 `job_type` 구분 없이 사용자별 활성 job(`pending`/`running`) 수를 카운트
  (`backend/app/api/upload_jobs.py:58-62`) → 채팅 job이 persona/product 업로드 job과
  `max_active_jobs_per_user=5` 한도를 공유. 멀티턴 대화 사용 패턴과 충돌 가능성 있었음.
- `_process_chat_job`/`_stream_chat_job_events`의 에러 이벤트가 `detail` 필드를 사용하는데,
  기존 `chat_v2_stream`/`crm_message_agent.chat_stream`은 `message` 필드를 사용 — 동일 프론트엔드
  파서를 재사용할 경우 필드명 불일치로 에러 메시지가 누락될 수 있었음.
- 두 사항 모두 설계 폐기로 검증 대상에서 제외. 새 게이팅 설계에는 해당하지 않음(참고로만 기록).

---

## 검증 결과 (게이팅 방식 — 2차 설계, 코드 리뷰 기준)

코드 리뷰 대상: `backend/app/api/marketing_api.py`(`chat_v2_stream`, line 325-482),
`backend/servers/crm_server.py`(lifespan, line 43-158), `backend/app/config/settings.py`
(line 240-241), `backend/app/api/crm_proxy.py`. 4개 파일 모두 `python -m py_compile` 통과.

### 1. 동시성 게이팅 동작
- [x] `asyncio.wait_for(semaphore.acquire(), timeout=chat_stream_admission_timeout)`로
      슬롯이 없으면 최대 60초 대기 후 슬롯 획득 시 정상 진행 (marketing_api.py:413-420)
- [x] 슬롯이 비면 `await`가 해제되어 바로 `agent.chat_stream(...)` 실행으로 이어짐
- [x] 대기 중 취소: `wait_for` 자체가 취소되면 `asyncio.Semaphore.acquire()`는 대기열에서
      깨끗이 제거되는 코루틴이라 슬롯 누수 없음(획득 전 취소이므로 release 대상 자체가 없음)
- [ ] **실제 동시 요청으로 슬롯 점유/대기열 동작을 라이브 테스트하지 못함** — Docker(Postgres/
      OpenSearch) 미가동으로 서버 기동 불가. 원 플랜 범위상 부하/동시성 검증은 별도 진행 예정.

### 2. 기존 기능 회귀 없음
- [x] SSE 이벤트 타입(`node_start`/`token`/`log`/`node_end`/`result`/`error`/`done`) 그대로 —
      `generate()` 내부에서 `chunk`를 가로채 파싱만 하고 `yield chunk`로 그대로 전달(456-460행),
      이벤트 페이로드 자체를 변형하지 않음
- [x] 최종 결과 구조 변경 없음 — `agent.chat_stream()` 호출 인자/처리 로직 자체는 게이팅 추가 전과 동일
- [x] keepalive — `chat_stream()` 내부(미변경 영역)에서 그대로 유지되는 것으로 확인(이 핸들러가
      keepalive를 직접 생성하지 않고 `agent.chat_stream`에 위임하는 구조이며 해당 함수는 손대지 않았음)

### 3. 에러 처리 회귀 없음
- [x] 잘못된 입력 처리 경로(컨버세이션 소유권 검증 등) 변경 없음 — 게이팅은 `agent.chat_stream` 호출
      직전에만 삽입되어 그 외 로직 영향 없음
- [x] `str(e)`/`traceback` 미노출 — 타임아웃 시 고정 한국어 메시지만 SSE로 전달(418행), 예외 처리도
      `type(e).__name__`만 로그(466행), 본문에는 고정 메시지만(472행)
- [x] 게이팅 타임아웃 시 `error`+`done` SSE 쌍으로 고정 한국어 메시지만 노출 — CLAUDE.md P3 준수

### 4. 코드 리뷰
- [x] 세마포어는 `lifespan`에서 1회 생성(`crm_server.py:113`), 요청마다 재생성되지 않음 (P4, P9)
- [x] `chat_stream_max_concurrent`(20), `chat_stream_admission_timeout`(60.0) 모두 `Settings`에
      정의 — 하드코딩 없음 (P6)
- [x] `finally: semaphore.release()`(476행)가 정상 종료/`CancelledError`/일반 예외 경로 모두를
      포괄하는 `try` 블록을 감싸고 있어 슬롯 반납 보장 (P8)
- [x] 1차 설계의 죽은 코드(plain `/chat/v2` job 큐, `upload_jobs`/`JobStatus`/`create_job`/
      `append_event` 등 임포트, `crm_proxy.py`의 `/chat/v2/jobs/{task_id}/stream` 프록시 라우트)
      전부 제거 확인 — grep 결과 `chat_job` 관련 흔적 0건

### 5. 프론트엔드
- [x] 변경 없음 — frontend-dev가 `Message.jsx`의 기존 에러 핸들링이 타임아웃 케이스를 그대로
      흡수함을 확인, 코드 수정 없이 종료

---

## 발견된 문제

발견된 문제 없음. 1차 설계 폐기 관련 사항은 위 "설계 변경 이력" 섹션 및 아래 1차 설계 리뷰
참고용 기록 참조 — 모두 폐기된 설계에만 해당하며 현재 코드에는 적용되지 않음.

## 미해결 항목 (후속 조치 필요)

- 동시 다중 요청 환경에서의 실제 슬롯 점유/대기열 동작 라이브 검증 — 별도 부하테스트에서 확인할 것
  (PASS 기준: 동시 20+ 요청 시 21번째부터 대기열에 들어가고, 앞 요청 완료 시 순차적으로 슬롯을 받아
  스트리밍이 시작되는지, 60초 초과 시 고정 에러 메시지로 깨끗이 종료되는지)

---

## API 계약 요약 (게이팅 도입 후 — 부하테스트 참고용)

```
POST /api/marketing/chat/v2/stream   (변경 없음)
요청: ChatRequest { user_input, session_id, conversation_id?, model?, file_records? }
응답: SSE stream (text/event-stream)
  event types: node_start, token, log, node_end, result, error, done
  result 페이로드: { status, thread_id, session_id, conversation_id,
                      recommended_products, generated_tasks, messages, logs, error }

내부 동작 변화:
  - 그래프 실행(`agent.chat_stream` 호출) 직전에 `asyncio.Semaphore(chat_stream_max_concurrent=20)`
    획득 필요. 슬롯이 없으면 SSE 연결은 유지한 채 최대 `chat_stream_admission_timeout=60`초 대기
  - 60초 내 슬롯을 못 받으면 `{"type":"error","message":"현재 요청이 많아..."}` + `{"type":"done"}`
    SSE를 보내고 정상 종료 (HTTP 레벨 에러 아님 — SSE 스트림 내부 이벤트로 처리)
  - 슬롯 획득 후 기존과 동일한 astream_events 기반 처리 진행, 종료 시(`finally`) 슬롯 반납
```

---

## 검증 통과 조건

- [x] 1번: 게이팅 동작 확인 완료 (코드 리뷰 기준; 라이브 부하 검증은 별도 진행)
- [x] 2번: SSE 이벤트/결과 회귀 없음 확인 완료
- [x] 3번: 에러 처리 회귀 없음 확인 완료
- [x] 4번: 코드 리뷰 통과
- [x] 5번: 해당 없음 (프론트엔드 변경 없음)

코드 리뷰 기준으로 모든 항목 통과. 이 보고서를 최종본으로 갱신함.
