# CRM Agent 코드 리뷰 및 개선 방안

## 1. 현재 아키텍처 요약

```
User Input
    ↓
[parse_crm_request_node]     ← LLM: 자연어 → 구조화된 요청
    ↓
[recommend_products_node]    ← LLM: 페르소나 분석 + 벡터 검색
    ↓
[HUMAN-IN-THE-LOOP]         ← 사용자가 3개 중 1개 선택
    ↓
[create_product_message_node] ← LLM: 마케팅 메시지 생성
    ↓
Complete
```

---

## 2. 잘한 점

| 항목 | 설명 |
|------|------|
| **Human-in-the-Loop** | LangGraph의 `interrupt_before`를 활용한 사용자 개입 설계가 적절함 |
| **모듈 분리** | nodes / services / prompts / state 분리가 명확함 |
| **타입 안정성** | `TypedDict`로 State를 세분화 (RequestContext, RecommendationContext 등) |
| **분석 캐싱** | 동일 페르소나에 대한 분석 결과를 DB에 캐싱하여 중복 LLM 호출 방지 |
| **Multi-Query 전략** | 단일 쿼리가 아닌 3~5개 다각도 쿼리로 검색 품질 향상 |
| **5x8 분석 프레임워크** | 5-Level x 8-Dimension 분석은 체계적이고 차별화된 접근 |

---

## 3. 개선이 필요한 점

### 3.1 에러 핸들링 부족 (심각도: 높음)

**현재 문제:**
- 외부 API 호출 (`requests.post`) 시 타임아웃, 네트워크 오류 처리가 거의 없음
- LLM 응답 파싱 실패 시 fallback이 부족함

**현업 방식:**
```python
# 현재 코드
response = requests.post(f"{API_BASE_URL}/api/personas/get", json=payload)
data = response.json()

# 현업 권장 코드
try:
    response = requests.post(
        f"{API_BASE_URL}/api/personas/get",
        json=payload,
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
except requests.exceptions.Timeout:
    logger.error("Persona API timeout")
    raise CRMServiceError("페르소나 정보 조회 시간 초과")
except requests.exceptions.HTTPError as e:
    logger.error(f"Persona API error: {e}")
    raise CRMServiceError(f"페르소나 API 오류: {e.response.status_code}")
```

**개선 방안:**
- 모든 외부 API 호출에 `timeout` 설정
- `retry` 로직 추가 (tenacity 라이브러리 권장)
- 커스텀 예외 클래스 도입 (`CRMServiceError`, `CRMParseError` 등)

---

### 3.2 설정값 하드코딩 (심각도: 중간)

**현재 문제:**
```python
# recommend_products.py에 하드코딩된 값들
API_BASE_URL = "http://host.docker.internal:8020"
SEARCH_API_URL = "http://host.docker.internal:8010"
model = ChatOpenAI(model="gpt-5-mini", temperature=0.7)
```

**현업 방식:**
```python
# config.py 또는 .env에서 관리
from pydantic_settings import BaseSettings

class CRMConfig(BaseSettings):
    api_base_url: str = "http://host.docker.internal:8020"
    search_api_url: str = "http://host.docker.internal:8010"
    llm_model: str = "gpt-5-mini"
    llm_temperature: float = 0.7
    search_top_k: int = 10

    class Config:
        env_prefix = "CRM_"
```

**개선 방안:**
- 환경변수 또는 config 파일로 분리
- 환경별(dev/staging/prod) 설정 관리

---

### 3.3 LLM 호출이 너무 많음 (심각도: 중간)

**현재 흐름에서 LLM 호출 횟수:**

| 단계 | LLM 호출 | 용도 |
|------|----------|------|
| parse_crm_request | 1회 | 사용자 입력 파싱 |
| recommend_persona | 1회 | 5x8 페르소나 분석 |
| generate_multi_queries | 1회 | 검색 쿼리 생성 |
| generate_message | 1회 | 마케팅 메시지 생성 |
| **합계** | **4회** | |

**현업 관점:**
- 요청 1건당 LLM 4회 호출은 **비용과 지연시간** 측면에서 부담
- 특히 페르소나 분석(5x8)의 프롬프트가 매우 길어서 토큰 소비가 큼

**개선 방안:**
- 페르소나 분석 + 쿼리 생성을 **1회 호출로 병합** 검토
- 파싱 단계는 LLM 대신 **규칙 기반 파서**로 대체 가능한지 검토
- 분석 결과 캐싱은 이미 잘 되어있으므로, 캐시 히트율을 높이는 전략 추가

---

### 3.4 벡터 검색 로직 (심각도: 중간)

**현재 문제:**
```python
# 쿼리별로 개별 API 호출 → N번 네트워크 왕복
for query in queries:
    results = self.search_single_query(query, product_ids, top_k)
    all_results.extend(results)
```

**현업 방식:**
```python
# 배치 검색 API 활용 또는 비동기 병렬 처리
import asyncio

async def search_all_queries(self, queries, product_ids, top_k):
    tasks = [
        self.async_search(query, product_ids, top_k)
        for query in queries
    ]
    results = await asyncio.gather(*tasks)
    return self.merge_results(results)
```

**개선 방안:**
- 멀티쿼리를 **병렬(async)** 로 실행하여 검색 지연 시간 단축
- 또는 OpenSearch의 `multi_search` API를 활용하여 1회 호출로 처리

---

### 3.5 프롬프트 관리 (심각도: 낮음)

**현재 문제:**
- `crm_parse_prompt.py`에 프롬프트가 긴 Python 문자열로 작성됨
- `crm_recommend_products.py`도 동일
- 반면 `create_product_message`는 이미 YAML로 분리되어 있어 **일관성 없음**

**현업 방식 (통일된 관리):**
```
prompts/
├── parse_request.yaml        # 파싱 프롬프트
├── persona_analysis.yaml     # 분석 프롬프트
├── query_generation.yaml     # 쿼리 생성 프롬프트
├── brand_tone.yaml           # 브랜드 톤 (기존)
└── purpose_prompt.yaml       # 목적별 프롬프트 (기존)
```

**개선 방안:**
- 이미 YAML을 일부 사용하고 있으므로, 나머지 프롬프트도 YAML로 통일
- 또는 반대로 현재 규모에서는 `.py` 파일로 통일해도 무방

---

### 3.6 로깅 및 관측성(Observability) (심각도: 중간)

**현재 문제:**
- `print()` 기반 디버깅
- 실행 시간 추적 없음
- LLM 입출력 로깅 없음

**현업 방식:**
```python
import structlog
logger = structlog.get_logger()

# LangSmith 또는 LangFuse 연동
from langsmith import traceable

@traceable(name="recommend_products")
def recommend_products(self, user_input, persona_id):
    logger.info("recommendation_started",
                persona_id=persona_id,
                input_length=len(user_input))
    ...
    logger.info("recommendation_completed",
                num_results=len(results),
                duration_ms=elapsed)
```

**개선 방안:**
- `print()` → `logging` 또는 `structlog`로 교체
- LangSmith/LangFuse 연동으로 LLM 호출 추적
- 각 노드 실행 시간 측정

---

### 3.7 테스트 코드 부재 (심각도: 높음)

**현재 문제:**
- 테스트 파일이 전혀 없음
- 서비스 로직을 검증할 수 없음

**현업 방식:**
```
tests/
├── test_parse_crm_request.py
├── test_recommend_products.py
├── test_create_product_message.py
└── test_workflow.py          # 통합 테스트
```

```python
# 예시: 파싱 서비스 단위 테스트
def test_parse_introduction_request():
    parser = MultiValueParser()
    result = parser.parse("페르소나1에게 라네즈 브랜드 소개 메시지 만들어줘")

    assert result["persona_id"] == "PERSONA_001"
    assert result["purpose"] == "브랜드/제품 첫소개"
    assert "라네즈" in result["brands"]
```

**개선 방안:**
- 최소한 각 서비스별 단위 테스트 작성
- LLM 호출은 mock 처리
- 워크플로우 통합 테스트는 LangGraph의 `test_utils` 활용

---

### 3.8 기타 개선 사항

| 항목 | 현재 | 권장 |
|------|------|------|
| `config/TODO_crm_constants.py` | 빈 파일 | 삭제하거나 실제 상수 정리 |
| `tools/TODO_tools.py` | 빈 파일 | 삭제하거나 Tool 구현 |
| Singleton 패턴 | 모듈 레벨 인스턴스 생성 | DI(의존성 주입) 또는 팩토리 패턴 검토 |
| `MemorySaver` | 인메모리 체크포인터 | 프로덕션에서는 Redis/DB 기반 체크포인터 필요 |

---

## 4. 현업 CRM Agent 아키텍처 비교

### 현업에서 추가로 고려하는 요소

```
┌─────────────────────────────────────────────────┐
│                   현업 CRM Agent                  │
├─────────────────────────────────────────────────┤
│                                                   │
│  [Rate Limiter]      ← API 호출 속도 제한          │
│  [Circuit Breaker]   ← 외부 서비스 장애 대응        │
│  [Retry Policy]      ← 재시도 정책                 │
│  [Input Validation]  ← 입력 검증 레이어             │
│  [Output Guard]      ← LLM 출력 검증 (할루시네이션)  │
│  [A/B Testing]       ← 프롬프트/모델 실험            │
│  [Monitoring]        ← 성능/비용/품질 모니터링        │
│  [Fallback]          ← LLM 실패 시 대체 응답        │
│                                                   │
└─────────────────────────────────────────────────┘
```

### 현재 프로젝트 vs 현업 비교표

| 항목 | 현재 프로젝트 | 현업 수준 | 갭 |
|------|-------------|----------|-----|
| 워크플로우 설계 | LangGraph + HITL | 동일 | 없음 |
| 타입 안정성 | TypedDict | Pydantic Model | 작음 |
| 에러 핸들링 | 기본적 | try/except + retry + circuit breaker | 큼 |
| 설정 관리 | 하드코딩 | 환경변수 + config | 중간 |
| 테스트 | 없음 | unit + integration + e2e | 큼 |
| 로깅 | print | structlog + LangSmith | 큼 |
| 모니터링 | 없음 | Prometheus + Grafana | 큼 |
| 프롬프트 관리 | .py + .yaml 혼재 | 통일된 방식 | 작음 |
| 검색 | 순차 멀티쿼리 | 병렬 또는 배치 | 중간 |
| 캐싱 | DB 분석 캐시 | + Redis 응답 캐시 | 중간 |
| 보안 | API key .env | + Secret Manager + 입력 sanitize | 중간 |

---

## 5. 우선순위별 개선 로드맵

### Phase 1: 즉시 개선 (1~2일)
- [ ] 에러 핸들링: 모든 외부 API 호출에 timeout + try/except 추가
- [ ] 하드코딩 제거: API URL, 모델명 등을 환경변수로 분리
- [ ] TODO 파일 정리: 빈 파일 삭제 또는 구현
- [ ] `print()` → `logging` 교체

### Phase 2: 단기 개선 (1주)
- [ ] 단위 테스트 작성 (각 서비스별 최소 3개)
- [ ] 벡터 검색 병렬화 (`asyncio.gather`)
- [ ] 프롬프트 관리 방식 통일
- [ ] 커스텀 예외 클래스 도입

### Phase 3: 중기 개선 (2~4주)
- [ ] LangSmith/LangFuse 연동
- [ ] 프롬프트 A/B 테스트 인프라
- [ ] MemorySaver → 영구 체크포인터 (Redis/PostgreSQL)
- [ ] LLM Output Guard (할루시네이션 검증)

### Phase 4: 장기 개선 (1~2개월)
- [ ] 모니터링 대시보드 구축
- [ ] Circuit Breaker 패턴 도입
- [ ] 멀티 에이전트 확장 (CRM + 고객응대 + 분석)
- [ ] LLM 호출 최적화 (호출 횟수 감소, 모델 티어링)

---

## 6. 총평

**현재 점수: 7/10**

코어 아키텍처(LangGraph + HITL + 모듈 분리 + 5x8 분석)는 **잘 설계**되어 있음. 특히 페르소나 기반 다차원 분석 프레임워크와 멀티쿼리 전략은 차별화 포인트.

다만 **프로덕션 준비도** 측면에서 에러 핸들링, 테스트, 로깅이 부족하여 실제 서비스 운영 시 안정성 이슈가 발생할 수 있음. Phase 1~2 개선만으로도 프로덕션 수준에 근접할 수 있으므로, 핵심 기능 개발 후 안정성 강화에 집중하는 것을 권장.
