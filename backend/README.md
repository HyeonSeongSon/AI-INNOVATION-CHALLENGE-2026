# backend

FastAPI 5개 마이크로서비스 + LangGraph 멀티에이전트.

이 문서는 **코드 탐색용 지도**입니다. 서비스 구성·포트는 [루트 README](../README.md),
구조와 요청 흐름 상세는 [README.detailed.md](../README.detailed.md) 3·4·8장,
코딩 규칙은 [CLAUDE.md](../CLAUDE.md)를 참고하세요.

## 어디를 보면 되는지

| 관심사 | 위치 |
|---|---|
| 요청 진입 — 인증·Rate Limit·BFF 프록시 | `main.py`, `app/api/` |
| 서비스별 기동 진입점 | `servers/` (crm·recommend·generate·data_registration) |
| 에이전트 그래프 | `app/agents/{crm_message,recommend_product,generate_message,data_registration}_agent/` |
| 에이전트 간 호출 (A2A) | `a2a/` — 193줄. `client.py`가 재시도·지수 백오프 담당 |
| 공용 인프라 | `app/core/` — `auth` · `logging` · `llm_factory` · `llm_utils` · `rate_limiter` |
| 설정 (167개 필드, 시작 시 필수 시크릿 검증) | `app/config/settings.py` |

에이전트 디렉터리는 공통으로 `workflow.py`(그래프 정의) · `nodes.py`(노드 구현) ·
`state.py`(TypedDict)를 가집니다. A2A로 호출되는 서브에이전트 3종(recommend ·
generate · data_registration)은 여기에 `a2a_agent.py`(A2A 진입점)와
`services/`(비즈니스 로직)가 더 있고, 이들을 오케스트레이션하는 `crm_message_agent`에는
없습니다.

## 읽는 순서 (처음이라면)

1. **`app/agents/crm_message_agent/nodes.py`** — supervisor 라우팅.
   `RouteDecision`(:120)의 `task_plan` 필드(:121)로 서브에이전트 실행 순서를 한 번에 결정하고,
   `supervisor_agent`(:181~)가 남은 task를 순차 소비한다(:197~260).
   그래프 배선 자체는 같은 디렉터리의 `workflow.py`(25줄)
2. **`app/agents/recommend_product_agent/services/recommend_product_in_persona.py`** —
   멀티벡터 retrieval → 페르소나 3차원 병렬 하이브리드 검색 → RRF 융합
3. **`app/agents/generate_message_agent/services/quality_check.py`** —
   3단계 품질 검사 (Rule → Semantic KNN → LLM-as-a-Judge)
4. **`app/core/llm_utils.py`** — `ainvoke_with_retry()`. 호출 지점별 세마포어 +
   Full Jitter 백오프. 부하테스트 39차에서 완료율을 56% → 100%로 올린 수정

## 로컬 실행

```bash
cp app/.env.example app/.env

# backend/ 에서 터미널 5개
uvicorn main:app --port 8005 --reload
uvicorn servers.crm_server:app --port 8006 --reload
uvicorn servers.recommend_server:app --port 8001 --reload
uvicorn servers.generate_server:app --port 8002 --reload
uvicorn servers.data_registration_server:app --port 8003 --reload
```

DB·OpenSearch가 먼저 떠 있어야 합니다. 전체 스택 절차는 [CLAUDE.md](../CLAUDE.md) 참고.
