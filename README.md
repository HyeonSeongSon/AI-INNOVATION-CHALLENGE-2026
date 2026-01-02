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
python setup_pipeline.py
```

이 스크립트는 다음 작업을 수행합니다:
- OpenSearch 인덱스 생성
- 제품 데이터 임베딩 생성
- 하이브리드 검색 파이프라인 설정

#### Step 2: PostgreSQL 초기화

```bash
cd database
python setup_pipeline.py
```

이 스크립트는 다음 작업을 수행합니다:
- 데이터베이스 테이블 생성 (personas, analysis_results, search_queries, products)
- 초기 페르소나 데이터 로드
- 제품 데이터 로드

#### Step 3: Docker Compose 실행

```bash
docker compose up
```

모든 서비스가 시작됩니다:
- **Backend API (CRM Agent)**: http://localhost:8005
- **Database API**: http://localhost:8020
- **OpenSearch API**: http://localhost:8010
- **OpenSearch Dashboards**: http://localhost:5601
- **pgAdmin**: http://localhost:5050

---

## API 엔드포인트

### 1. CRM Agent API (Port 8005)

#### POST `/api/crm/generate`

CRM 메시지 생성 시작 (1단계)

**요청 예시:**
```json
{
  "user_input": "{\"persona_id\": \"PERSONA_002\", \"purpose\": \"신상품홍보\", \"product_categories\": [\"립스틱\"]}",
  "thread_id": null
}
```

**응답 예시:**
```json
{
  "status": "needs_selection",
  "thread_id": "thread-abc123",
  "recommended_products": [
    {
      "product_id": "PROD001",
      "product_name": "벨벳 매트 립스틱",
      "brand": "브랜드A",
      "sale_price": 25000,
      "vector_search_score": 0.95
    }
  ],
  "count": 3
}
```

#### POST `/api/crm/select-product`

사용자 제품 선택 처리 (2단계)

**요청 예시:**
```json
{
  "thread_id": "thread-abc123",
  "selected_product_id": "PROD001"
}
```

**응답 예시:**
```json
{
  "status": "completed",
  "thread_id": "thread-abc123",
  "final_message": {
    "카피문구": "당신을 위한 완벽한 립스틱",
    "본문": "...",
    "버튼": "지금 구매하기"
  }
}
```

#### GET `/api/crm/health`

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
├── backend/                 # FastAPI 백엔드
│   ├── app/
│   │   ├── api/            # API 라우터
│   │   └── service/        # 비즈니스 로직
│   │       ├── agent/      # AI 에이전트
│   │       └── tools/      # 도구 (제품 추천 등)
├── database/               # PostgreSQL 관련
│   ├── api_endpoints.py    # DB API
│   ├── setup_pipeline.py   # DB 초기화
│   └── models.py          # SQLAlchemy 모델
├── opensearch/            # OpenSearch 관련
│   ├── opensearch_api.py  # OpenSearch API
│   └── setup_pipeline.py  # OpenSearch 초기화
└── docker-compose.yml     # Docker Compose 설정
```

### 주요 워크플로우

#### 1. 제품 추천 워크플로우

```
사용자 요청
    ↓
페르소나 정보 조회 (DB API)
    ↓
기존 분석 결과 확인 (DB API)
    ↓
없으면 → 페르소나 분석 수행 (LLM) → DB 저장
    ↓
멀티 쿼리 생성 (LLM)
    ↓
쿼리 DB 저장
    ↓
하이브리드 검색 (OpenSearch)
    ↓
상위 3개 제품 반환
```

#### 2. CRM 메시지 생성 워크플로우

```
1단계: /api/crm/generate
    ↓
LLM이 도구 선택 (Tool Calling)
    ↓
recommend_products 실행
    ↓
Interrupt 발생 → 제품 목록 반환
    ↓
2단계: 사용자가 제품 선택
    ↓
/api/crm/select-product
    ↓
create_product_message 실행
    ↓
최종 CRM 메시지 생성
```

---

## 라이선스

MIT License

---

## 문의

프로젝트 관련 문의사항은 이슈를 생성해주세요.
