# AI Innovation Challenge 2026

페르소나 기반 뷰티 제품 추천 및 CRM 메시지 생성 시스템

## 목차

- [프로젝트 개요](#프로젝트-개요)
- [시스템 아키텍처](#시스템-아키텍처)
- [환경 구축](#환경-구축)
- [API 엔드포인트](#api-엔드포인트)
- [개발 가이드](#개발-가이드)

---

## 프로젝트 개요

이 프로젝트는 페르소나 정보를 기반으로 뷰티 제품을 추천하고, 맞춤형 CRM 메시지를 생성하는 AI 시스템입니다.

### 주요 기능

- **페르소나 기반 제품 추천**: 다단계×다차원 분석을 통한 맞춤형 제품 추천
- **하이브리드 검색**: OpenSearch를 활용한 BM25 + KNN 하이브리드 검색
- **CRM 메시지 생성**: AI 에이전트 기반 자동 메시지 생성
- **데이터 관리**: PostgreSQL 기반 페르소나, 분석 결과, 검색 쿼리 관리

---

## 시스템 아키텍처

```
┌─────────────────────────┐
│       Client            │
└───────────┬─────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────┐
│                  FastAPI Services                     │
│                                                       │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  Backend API     │    │   Database API   │       │
│  │  (Port 8005)     │    │   (Port 8020)    │       │
│  │  - CRM Agent     │    │   - Personas     │       │
│  └──────────────────┘    │   - Analysis     │       │
│                          │   - Products     │       │
│  ┌──────────────────┐    └──────────────────┘       │
│  │ OpenSearch API   │                                │
│  │  (Port 8010)     │                                │
│  │  - Hybrid Search │                                │
│  └──────────────────┘                                │
└───────────────────────────────────────────────────────┘
            │                           │
            ▼                           ▼
┌────────────────────────┐   ┌──────────────────────┐
│   OpenSearch Cluster   │   │   PostgreSQL DB      │
│   - Node 1 (9200)      │   │   (5432)             │
│   - Node 2 (9201)      │   │   + pgAdmin (5050)   │
│   - Node 3 (9202)      │   └──────────────────────┘
│   + Dashboards (5601)  │
└────────────────────────┘
```

---

## 환경 구축

### 1. 사전 요구사항

- Docker & Docker Compose
- Python 3.9+
- OpenAI API Key

### 2. 환경 변수 설정

각 디렉토리에 제공된 `.env.example` 파일을 복사하여 `.env` 파일을 생성하세요:

#### Backend API 환경 변수
```bash
# 위치: backend/app/.env.example → backend/app/.env
cp backend/app/.env.example backend/app/.env
```

`.env` 파일 내용:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

#### Database API 환경 변수
```bash
# 위치: database/.env.example → database/.env
cp database/.env.example database/.env
```

`.env` 파일 내용:
```bash
# PostgreSQL 데이터베이스 설정
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_innovation_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123

# pgAdmin 설정
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin123
PGADMIN_PORT=5050
```

#### OpenSearch API 환경 변수
```bash
# 위치: opensearch/.env.example → opensearch/.env
cp opensearch/.env.example opensearch/.env
```

`.env` 파일 내용:
```bash
# OpenSearch 연결 설정
OPENSEARCH_ADMIN_PASSWORD=MyStrongPassword123!
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

# FastAPI 설정
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8010

# 환경 (local, production)
ENVIRONMENT=local
```

**중요**: `backend/app/.env` 파일의 `OPENAI_API_KEY`를 실제 OpenAI API 키로 변경하세요!

### 3. 초기 데이터 설정

#### Step 1: OpenSearch 초기화

```bash
cd opensearch
python setup_opensearch.py
```

이 스크립트는 다음 작업을 수행합니다:
- OpenSearch 인덱스 생성
- 제품 데이터 임베딩 생성
- 하이브리드 검색 파이프라인 설정

#### Step 2: PostgreSQL 초기화

```bash
cd database
python scripts/setup_pipeline.py
```

이 스크립트는 다음 작업을 수행합니다:
- 데이터베이스 테이블 생성 (personas, analysis_results, search_queries, products)
- 초기 페르소나 데이터 로드
- 제품 데이터 로드

#### Step 3: Docker Compose 실행

```bash
# 최초 1회 네트워크 생성 필요
docker network create msa-net

cd opensearch && docker compose up -d
cd database   && docker compose up -d
cd backend    && docker compose up
```

모든 서비스가 시작됩니다:
- **API Gateway**: http://localhost:8005
- **Frontend**: http://localhost:3000
- **Database API**: http://localhost:8020
- **OpenSearch API**: http://localhost:8010
- **OpenSearch Dashboards**: http://localhost:5601
- **pgAdmin**: http://localhost:5050

---

## API 엔드포인트

### 1. API Gateway (Port 8005)

#### POST `/api/marketing/chat/v2`

CRM 메시지 생성 (단건 응답)

**요청 예시:**
```json
{
  "message": "PERSONA_002에게 신상품 립스틱 홍보 메시지 만들어줘",
  "conversation_id": null
}
```

**응답 예시:**
```json
{
  "conversation_id": "conv-abc123",
  "status": "completed",
  "answer": "...",
  "logs": ["[Step 1] 상품 검색 중...", "[Step 2] 메시지 생성 중..."]
}
```

#### POST `/api/marketing/chat/v2/stream`

CRM 메시지 생성 (SSE 스트리밍). `text/event-stream` 응답.

이벤트 타입: `node_start` / `token` / `text_chunk` / `text_done` / `log` / `node_end` / `result` / `error` / `done`

#### 인증 관련

| 메서드 | 경로 | 역할 |
|--------|------|------|
| POST | `/auth/register` | 회원가입 |
| POST | `/auth/login` | 로그인 → HttpOnly 쿠키 발급 |
| POST | `/auth/refresh` | access 토큰 갱신 |
| POST | `/auth/logout` | 로그아웃 + 쿠키 삭제 |
| GET  | `/auth/me` | 내 정보 조회 |

#### GET `/health`

헬스 체크

---

### 2. Database API (Port 8020)

#### POST `/api/personas`

페르소나 생성

**요청 예시:**
```json
{
  "persona_id": "PERSONA_001",
  "name": "김지현",
  "age": 28,
  "skin_type": ["지성", "복합성"],
  "skin_concerns": ["모공", "칙칙함"]
}
```

#### POST `/api/personas/get`

페르소나 정보 조회

**요청 예시:**
```json
{
  "persona_id": "PERSONA_001"
}
```

#### POST `/api/analysis-results`

분석 결과 생성

**요청 예시:**
```json
{
  "persona_id": "PERSONA_001",
  "analysis_result": "{\"multi_level_analysis\": {...}, \"multi_dimensional_analysis\": {...}}"
}
```

**응답 예시:**
```json
{
  "analysis_id": 1,
  "persona_id": "PERSONA_001",
  "analysis_created_at": "2024-01-01T12:00:00"
}
```

#### POST `/api/analysis-results/get`

분석 결과 조회

**요청 예시:**
```json
{
  "persona_id": "PERSONA_001"
}
```

**응답 예시:**
```json
[
  {
    "analysis_id": 1,
    "persona_id": "PERSONA_001",
    "analysis_result": "{...}",
    "analysis_created_at": "2024-01-01T12:00:00"
  }
]
```

#### POST `/api/search-queries`

검색 쿼리 생성

**요청 예시:**
```json
{
  "analysis_id": 1,
  "search_query": "지성 피부 모공 케어 세럼"
}
```

**응답 예시:**
```json
{
  "query_id": 1,
  "analysis_id": 1,
  "search_query": "지성 피부 모공 케어 세럼",
  "query_created_at": "2024-01-01T12:00:00"
}
```

#### POST `/api/search-queries/get`

검색 쿼리 조회

**요청 예시:**
```json
{
  "analysis_id": 1
}
```

#### POST `/api/products`

상품 생성

**요청 예시:**
```json
{
  "product_id": "A20251200001",
  "product_name": "수분 세럼 50ml",
  "brand": "설화수",
  "rating": 4.5,
  "sale_price": 40000
}
```

#### POST `/api/products/filter`

상품 필터링 조회

**요청 예시:**
```json
{
  "brands": ["설화수", "헤라"],
  "skin_type": ["지성", "복합성"],
  "skin_concerns": ["모공", "칙칙함"]
}
```

#### GET `/api/health`

헬스 체크

---

### 3. OpenSearch API (Port 8010)

#### GET `/api/product/{product_id}`

Product ID로 단일 상품 조회

**요청 예시:**
```
GET /api/product/PROD001?index_name=product_index
```

**응답 예시:**
```json
{
  "success": true,
  "product_id": "PROD001",
  "document": {
    "product_id": "PROD001",
    "상품명": "벨벳 매트 립스틱",
    "브랜드": "브랜드A",
    "문서": "..."
  }
}
```

#### POST `/api/search/product-ids`

Product ID 리스트로 필터링된 하이브리드 검색

**요청 예시:**
```json
{
  "query": "촉촉한 립스틱",
  "product_ids": ["PROD001", "PROD002", "PROD003"],
  "index_name": "product_index",
  "pipeline_id": "hybrid-minmax-pipeline",
  "top_k": 3
}
```

**응답 예시:**
```json
{
  "success": true,
  "total_results": 3,
  "query": "촉촉한 립스틱",
  "product_id_filter": ["PROD001", "PROD002", "PROD003"],
  "results": [
    {
      "score": 0.95,
      "product_id": "PROD001",
      "브랜드": "브랜드A",
      "상품명": "벨벳 매트 립스틱",
      "문서": "..."
    }
  ]
}
```

#### GET `/health`

헬스 체크

---

## 개발 가이드

### 브랜치 전략

개인 작업은 각자 브랜치를 생성하여 작업하고, `main` 브랜치에는 병합된 최종 결과물만 올립니다.

```bash
# 새 브랜치 생성
git checkout -b feature/your-feature-name

# 작업 후 커밋
git add .
git commit -m "feat: your feature description"

# main 브랜치에 병합
git checkout main
git merge feature/your-feature-name
```

### 프로젝트 구조

```
AI-INNOVATION-CHALLENGE-2026/
├── backend/                      # FastAPI 백엔드 (5개 마이크로서비스)
│   ├── main.py                   # API Gateway (port 8005)
│   ├── servers/                  # 각 서비스 진입점 (8001/8002/8003/8006)
│   ├── app/
│   │   ├── api/                  # API 라우터 (auth, crm_proxy, db_proxy 등)
│   │   ├── agents/               # LangGraph 에이전트 (crm/recommend/generate/data_reg)
│   │   ├── core/                 # 인프라 (auth, logging, llm_factory 등)
│   │   └── config/settings.py    # 환경변수 중앙 관리
│   └── a2a/                      # Agent-to-Agent 내부 통신 프로토콜
├── database/                     # PostgreSQL + Database API (port 8020)
│   ├── api_server.py             # Database API 진입점
│   ├── routers/                  # API 라우터 (personas, products, conversations 등)
│   ├── core/                     # ORM 모델, DB 설정
│   ├── init/                     # 초기화 SQL (01~07)
│   └── scripts/setup_pipeline.py # DB 초기화 스크립트
├── opensearch/                   # OpenSearch + 검색 API (port 8010)
│   ├── opensearch_api.py         # OpenSearch API 진입점
│   ├── opensearch_hybrid.py      # 하이브리드 검색 클라이언트
│   └── setup_opensearch.py       # 인덱스/파이프라인 초기화 스크립트
└── frontend/                     # React 19 + Vite 7 (port 3000)
    └── src/                      # 컴포넌트, 페이지, Context
```

### 주요 워크플로우

#### CRM 메시지 생성 워크플로우

```
POST /api/marketing/chat/v2/stream (SSE)
    ↓
[Gateway] JWT 인증 + Rate Limit 확인
    ↓
[CRM Supervisor] LLM이 task_plan 결정
    ↓
[Recommend Agent :8001]
  페르소나 검색 쿼리 조회/생성 → OpenSearch 하이브리드 검색
  → 멀티벡터 retrieval(top-100) → RRF 융합 → top-3 추천
    ↓
[Generate Agent :8002]
  메시지 생성 → 3단계 품질 검사
  (Rule → Semantic 유사도 → LLM Judge) → 실패 시 피드백 재생성
    ↓
[CRM Supervisor] 최종 응답 조합 → SSE done 이벤트
```

---

## 라이선스

MIT License

---

## 문의

프로젝트 관련 문의사항은 이슈를 생성해주세요.
