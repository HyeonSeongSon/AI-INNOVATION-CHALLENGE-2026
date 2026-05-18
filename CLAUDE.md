# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

페르소나 기반 뷰티 상품 추천 및 CRM 메시지 자동 생성 시스템.
LangGraph 멀티에이전트 백엔드 + FastAPI REST/SSE + OpenSearch 벡터 검색.

---

## Services & Ports

| Service | Port | Entry Point | Docker Compose |
|---------|------|-------------|----------------|
| Backend API (CRM Agent) | 8005 | `backend/main.py` | `backend/docker-compose.yml` |
| Recommend Agent | 8001 | `backend/servers/recommend_server.py` | `backend/docker-compose.yml` |
| Generate Agent | 8002 | `backend/servers/generate_server.py` | `backend/docker-compose.yml` |
| Data Registration Agent | 8003 | `backend/servers/data_registration_server.py` | `backend/docker-compose.yml` |
| Database API | 8020 | `database/api_endpoints.py` | `database/docker-compose.yml` |
| OpenSearch API | 8010 | `opensearch/opensearch_api.py` | `opensearch/docker-compose.yml` |
| Frontend | 3000 | `frontend/` | `frontend/docker-compose.yml` |

## Running the Backend

```bash
cp backend/app/.env.example backend/app/.env

# backend/ 디렉터리에서 터미널 4개
uvicorn main:app --port 8005 --reload
uvicorn servers.recommend_server:app --port 8001 --reload
uvicorn servers.generate_server:app --port 8002 --reload
uvicorn servers.data_registration_server:app --port 8003 --reload
```

## Full Stack (Docker)

```bash
cd opensearch && python setup_pipeline.py
cd database   && python setup_pipeline.py
cd opensearch && docker compose up -d
cd database   && docker compose up -d
cd backend    && docker compose up
```

## LangGraph Studio

```bash
langgraph dev   # 루트에서 실행
```

그래프: `marketing_assistant` / `crm_message_agent` / `product_recommend_agent` / `generate_message_agent`

---

## Architecture

### Agent Hierarchy

```
POST /api/marketing/chat/v2
 └── CRMMessageAgent                    crm_message_agent/crm_message_agent.py
      └── supervisor workflow            crm_message_agent/workflow.py
           ├── supervisor_agent          RouteDecision → Command(goto=...)
           ├── search_agent              도구 기반 DB/Search 조회
           ├── recommend_product_agent   → subgraph (port 8001)
           ├── generate_message_agent    → subgraph (port 8002)
           └── data_registration_agent   → subgraph (port 8003)
```

### Key Files

| 파일 | 역할 |
|------|------|
| `backend/main.py` | FastAPI 앱, lifespan에서 agent/graph 초기화 |
| `backend/app/config/settings.py` | 환경변수 → `Settings` 싱글턴 |
| `backend/app/core/llm_factory.py` | `get_llm(model, temperature)` |
| `backend/app/core/logging.py` | `AgentLogger`, `get_logger` |
| `backend/app/agents/base/base_state.py` | 모든 state의 기반 TypedDict |
| `backend/a2a/models.py` | A2A 프로토콜 공통 모델 |

### State 구조

```python
state["messages"]      # LangChain message list
state["status"]        # "running" | "completed" | "error"
state["logs"]          # 프론트엔드용 "[Step N] 메시지" 리스트
state["intermediate"]  # 에이전트 간 중간 결과
state["decisions"]     # supervisor 라우팅 이력
state["node_history"]  # 노드 실행 순서

state["active_persona_id"]  # conversation-scope 페르소나 ID — CRMMessageAgentState 직접 필드

state["intermediate"] = {
    "recommended_products": [...],
    "generated_tasks": [...],
}
```

---

## Coding Guidelines

### 1. Think Before Coding

구현 전에:
- 가정을 명시적으로 서술. 불확실하면 질문.
- 여러 해석이 가능하면 침묵 말고 옵션 제시.
- 더 단순한 접근이 있으면 먼저 언급.

### 2. Simplicity First

- 요청된 것만 구현. 추측성 기능, 미래 대비 추상화 금지.
- 단일 사용처에 인터페이스/추상 클래스 생성 금지.
- 200줄로 쓸 수 있으면 50줄로.
- 불가능한 시나리오에 대한 에러 핸들링 금지.

### 3. Surgical Changes

- 요청과 직접 관련 없는 코드는 건드리지 않는다.
- 인접 코드 개선, 포맷 변경, 리팩터 금지.
- 내 변경으로 생긴 dead import/variable만 제거. 기존 dead code는 언급만.

---

## Production-Level Code Patterns

이 섹션은 프로덕션에서 안정적으로 동작하는 코드를 작성하기 위한 구체적 패턴을 정의한다.
새 코드를 작성하거나 기존 코드를 수정할 때 아래 패턴을 따른다.

---

### P1. 타입 안전성 — 모든 경계에 타입을 명시한다

**함수 시그니처**: 인자와 반환값에 항상 타입 힌트.

```python
# Bad
def get_products(query, limit=10):
    ...

# Good
async def get_products(query: str, limit: int = 10) -> list[ProductDoc]:
    ...
```

**Pydantic v2로 외부 데이터 검증**: API 입력, LLM 응답, 외부 서비스 응답은 반드시 모델 경유.

```python
class RecommendRequest(BaseModel):
    persona_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=50)

    model_config = ConfigDict(extra="forbid")  # 정의되지 않은 필드 거절
```

**LLM structured output**: `dict`로 파싱하지 말고 Pydantic 모델로 직접 바인딩.

```python
class RouteDecision(BaseModel):
    next: Literal["recommend_product_agent", "generate_message_agent", "end"]
    reason: str

llm_with_structure = llm.with_structured_output(RouteDecision)
decision: RouteDecision = await llm_with_structure.ainvoke(messages)
```

---

### P2. 비동기 일관성 — async 컨텍스트에서 블로킹 I/O 금지

```python
# Bad — 이벤트 루프 전체를 차단
import requests
response = requests.get(url)

import time
time.sleep(1)

# Good
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)

import asyncio
await asyncio.sleep(1)
```

**CPU 바운드 작업**(이미지 처리, 대용량 JSON 파싱 등)은 `asyncio.to_thread`로 분리:

```python
result = await asyncio.to_thread(heavy_cpu_function, data)
```

---

### P3. 에러 처리 — 명시적이고 복구 가능한 에러

**에이전트 노드**: 예외를 삼키지 말 것. 에러 상태를 state에 기록하고 supervisor로 반환.

```python
async def recommend_node(state: RecommendState, config: RunnableConfig):
    try:
        result = await search_service.query(state["query"])
        return {"intermediate": {**state["intermediate"], "recommended_products": result}}
    except SearchServiceError as e:
        logger.error("search_failed", error=str(e))
        return Command(goto="supervisor", update={"status": "error", "error_message": str(e)})
```

**FastAPI 엔드포인트**: 구체적인 예외 타입을 잡고 적절한 HTTP 상태코드 반환.

```python
@router.post("/chat/v2")
async def chat(request: ChatRequest):
    try:
        return await agent.run(request)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except AgentTimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out")
    # Exception은 middleware에서 처리 — 여기서 catch하지 않음
```

**에러를 silently swallow하는 패턴 금지**:

```python
# Bad
try:
    result = await something()
except Exception:
    result = None  # 에러가 사라짐

# Good
try:
    result = await something()
except SomethingError as e:
    logger.warning("fallback_used", reason=str(e))
    result = default_value  # 폴백 의도를 명시
```

---

### P4. 리소스 관리 — 반드시 명시적으로 닫는다

**HTTP 클라이언트**: 요청마다 생성하지 말고 lifespan에서 관리.

```python
# main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await app.state.http_client.aclose()
```

**DB 커넥션**: 커넥션 풀을 lifespan에서 초기화, `async with` 로 세션 관리.

```python
async with db_pool.acquire() as conn:
    rows = await conn.fetch(query, *params)
```

**LangGraph 그래프 인스턴스**: lifespan에서 한 번만 컴파일, 요청마다 재컴파일 금지.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = workflow.compile(checkpointer=checkpointer)
    app.state.graph = graph
    yield
```

---

### P5. 로깅 — 검색 가능하고 상관관계 추적 가능한 로그

**구조화 로그**: f-string 메시지에 데이터를 섞지 말고 키-값 분리.

```python
# Bad
logger.info(f"상품 검색 완료: {len(results)}개, 쿼리: {query}")

# Good
logger.info("products_searched", count=len(results), query=query, persona_id=persona_id)
```

**노드 내부**: `AgentLogger` 사용 — system log + `state["logs"]` 동시 기록.

```python
log = AgentLogger(state, node_name="recommend_product")
log.info("search_started", query=state["query"])
# → structlog JSON (시스템) + state["logs"]에 "[Step N] search_started" 추가
```

**서비스 내부**: `get_logger(name)` — 시스템 로그만.

```python
logger = get_logger("search_service")
logger.debug("opensearch_query", index=index_name, size=top_k)
```

**절대 로그에 남기면 안 되는 것**: API 키, 비밀번호, 개인식별정보(이메일, 전화번호).

---

### P6. 설정 관리 — 하드코딩 금지

**모든 설정값은 `Settings`에서**: URL, 타임아웃, 모델명, 인덱스명을 코드에 직접 작성하지 않는다.

```python
# Bad
client = OpenSearch(hosts=["https://localhost:9200"])
llm = get_llm("claude-opus-4-7", temperature=0.7)

# Good
from app.config.settings import settings
client = OpenSearch(hosts=[settings.opensearch_url])
llm = get_llm(settings.llm_model, temperature=settings.llm_temperature)
```

**환경변수 기본값**: 개발용 기본값은 허용, 프로덕션 시크릿은 기본값 없이 required로.

```python
class Settings(BaseSettings):
    opensearch_url: str = "http://localhost:9200"   # 로컬 기본값 OK
    anthropic_api_key: str                           # required, 기본값 없음
    database_url: str                                # required
```

---

### P7. LangGraph 노드 설계 — 순수하고 결정적인 노드

**노드는 순수 함수에 가깝게**: 같은 state 입력 → 같은 방향의 출력. 부작용(DB 쓰기, 외부 API)은 명확히 표현.

**상태 업데이트는 반환값으로만**: 노드 내부에서 state를 직접 변경하지 않는다.

```python
# Bad
async def node(state, config):
    state["intermediate"]["result"] = data  # 직접 변경
    return state

# Good
async def node(state, config):
    return {"intermediate": {**state["intermediate"], "result": data}}
```

**서브그래프 thread_id 패턴 유지**: 부모 thread_id에 suffix 추가로 격리.

```python
sub_config = {
    "configurable": {
        "thread_id": f"{config['configurable']['thread_id']}:recommend"
    }
}
result = await subgraph.ainvoke(input_state, sub_config)
```

**노드 타임아웃**: LLM 노드는 `RunnableConfig`로 타임아웃 설정.

```python
result = await llm.ainvoke(messages, config={"timeout": 60})
```

---

### P8. FastAPI 엔드포인트 설계

**요청/응답 스키마 분리**: 같은 데이터라도 입력/출력 모델을 별도로 정의.

```python
class ChatRequest(BaseModel):    # 입력
    message: str
    thread_id: str | None = None

class ChatResponse(BaseModel):   # 출력
    thread_id: str
    status: str
    logs: list[str]
```

**SSE 스트리밍**: LangGraph `astream_events`를 `StreamingResponse`로 래핑.

```python
async def event_generator():
    async for event in graph.astream_events(input, config, version="v2"):
        if event["event"] == "on_chain_stream":
            yield f"data: {json.dumps(event['data'])}\n\n"

return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**헬스체크 엔드포인트**: 항상 구현. 의존 서비스 연결 확인 포함.

```python
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    # DB, OpenSearch 연결 확인
    await db_pool.fetchval("SELECT 1")
    return {"status": "ready"}
```

---

### P9. 의존성 주입 패턴

서비스 인스턴스를 함수 내부에서 직접 생성하지 않는다. FastAPI `Depends` 또는 lifespan에서 주입.

```python
# Bad — 요청마다 새 인스턴스
@router.post("/recommend")
async def recommend(request: RecommendRequest):
    service = SearchService(settings.opensearch_url)  # 매번 생성
    return await service.search(request.query)

# Good — lifespan에서 초기화된 인스턴스 재사용
def get_search_service(request: Request) -> SearchService:
    return request.app.state.search_service

@router.post("/recommend")
async def recommend(
    request: RecommendRequest,
    search_service: SearchService = Depends(get_search_service),
):
    return await search_service.search(request.query)
```

---

### P10. 보안 체크리스트

새 코드 작성 또는 수정 시 확인:

- [ ] 외부 입력(HTTP 요청, LLM 응답, 크롤링 데이터)은 Pydantic으로 검증
- [ ] DB 쿼리에 f-string / 문자열 포맷 삽입 금지 → 파라미터 바인딩 사용
- [ ] LLM 프롬프트에 사용자 입력을 그대로 삽입하지 않음 → 역할 분리(system/user 구분)
- [ ] API 키, 비밀번호를 로그, state, 응답 바디에 포함하지 않음
- [ ] CORS `allow_origins=["*"]` 금지 → 명시적 도메인 목록
- [ ] 파일 경로를 사용자 입력으로 구성할 때 path traversal 방지

---

**이 가이드라인이 잘 지켜지고 있다면**: diff에 불필요한 변경이 없고, 타입 오류가 런타임이 아닌 IDE에서 잡히며, 에러가 발생했을 때 로그만으로 원인을 찾을 수 있다.
