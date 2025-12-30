# AI Innovation Challenge 2026 - 화장품 추천 시스템 (Database)

AI 기반 개인 맞춤형 화장품 추천 시스템의 데이터베이스 레이어입니다. PostgreSQL + FastAPI + OpenSearch를 활용하여 사용자의 피부 타입, 고민, 선호도에 맞는 화장품을 추천합니다.

## 📋 목차

- [프로젝트 개요](#-프로젝트-개요)
- [기술 스택](#-기술-스택)
- [데이터베이스 구조](#-데이터베이스-구조)
- [설치 및 실행](#-설치-및-실행)
- [API 사용법](#-api-사용법)
- [데이터 마이그레이션](#-데이터-마이그레이션)

---

## 🎯 프로젝트 개요

### 주요 기능

1. **페르소나 기반 분석**
   - 사용자의 피부 타입, 고민, 선호 성분 등을 페르소나로 저장
   - 페르소나별 분석 결과 및 검색 쿼리 관리

2. **상품 데이터 관리**
   - 브랜드, 가격, 평점, 리뷰 등 상품 정보 관리
   - TEXT[] 배열을 활용한 페르소나 매칭 속성 저장
   - OpenSearch 벡터 검색 연동 (vectordb_id)

3. **분석 & 검색 이력**
   - 페르소나별 분석 결과 저장
   - 분석에 기반한 검색 쿼리 이력 관리

### 시스템 아키텍처

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   FastAPI   │─────▶│ PostgreSQL  │
│   (React)   │◀─────│   Backend   │◀─────│   Database  │
└─────────────┘      └─────────────┘      └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │  OpenSearch │
                     │ (Vector DB) │
                     └─────────────┘
```

---

## 🛠 기술 스택

### Backend
- **FastAPI 0.111.0** - 고성능 Python 웹 프레임워크
- **SQLAlchemy 2.0.45** - Python ORM
- **Pydantic 2.12.5** - 데이터 검증 및 직렬화
- **Uvicorn 0.30.0** - ASGI 서버

### Database
- **PostgreSQL 14+** - 메인 데이터베이스
- **psycopg2-binary 2.9.11** - PostgreSQL 드라이버

### Vector Search
- **OpenSearch 2.4.2** - 벡터 검색 엔진
- **LangChain 0.3.26** - LLM 애플리케이션 프레임워크
- **Sentence Transformers 2.7.0** - 임베딩 생성

---

## 🗄 데이터베이스 구조

### ERD (Entity Relationship Diagram)

```
┌─────────────────┐
│    personas     │
├─────────────────┤
│ persona_id (PK) │◀──┐
│ name            │   │
│ gender          │   │
│ age             │   │
│ skin_type[]     │   │
│ skin_concerns[] │   │
│ ...             │   │
└─────────────────┘   │
         │            │
         │ 1:N        │
         │            │
         ▼            │
┌─────────────────────┤
│ analysis_results    │
├─────────────────────┤
│ analysis_id (PK)    │
│ persona_id (FK)     │──┘
│ analysis_result     │
│ analysis_created_at │
└─────────────────────┘
         │
         │ 1:N
         │
         ▼
┌─────────────────┐
│ search_queries  │
├─────────────────┤
│ query_id (PK)   │
│ analysis_id (FK)│
│ search_query    │
│ query_created_at│
└─────────────────┘


┌─────────────────┐
│    products     │
├─────────────────┤
│ product_id (PK) │
│ vectordb_id     │ ← OpenSearch 연동
│ product_name    │
│ brand           │
│ product_tag     │
│ rating          │
│ review_count    │
│ sale_price      │
│ skin_type[]     │
│ skin_concerns[] │
│ preferred_colors│
│ product_image[] │
│ ...             │
└─────────────────┘
```

### 테이블 상세 설명

#### 1. `personas` - 페르소나 정보

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| persona_id | VARCHAR(100) | 페르소나 ID | PRIMARY KEY |
| name | VARCHAR(200) | 페르소나 이름 | NOT NULL |
| gender | VARCHAR(20) | 성별 | |
| age | INTEGER | 나이 | |
| occupation | VARCHAR(100) | 직업 | |
| skin_type | TEXT[] | 피부 타입 배열 | DEFAULT [] |
| skin_concerns | TEXT[] | 피부 고민 배열 | DEFAULT [] |
| personal_color | VARCHAR(50) | 퍼스널 컬러 | |
| shade_number | INTEGER | 셰이드 번호 | |
| preferred_colors | TEXT[] | 선호 색상 | DEFAULT [] |
| preferred_ingredients | TEXT[] | 선호 성분 | DEFAULT [] |
| avoided_ingredients | TEXT[] | 기피 성분 | DEFAULT [] |
| preferred_scents | TEXT[] | 선호 향 | DEFAULT [] |
| values | TEXT[] | 가치관 | DEFAULT [] |
| skincare_routine | VARCHAR(100) | 스킨케어 루틴 | |
| main_environment | VARCHAR(100) | 주 활동 환경 | |
| preferred_texture | TEXT[] | 선호 제형 | DEFAULT [] |
| pets | VARCHAR(50) | 반려동물 유무 | |
| avg_sleep_hours | INTEGER | 평균 수면 시간 | |
| stress_level | VARCHAR(50) | 스트레스 수준 | |
| digital_device_usage_time | INTEGER | 디지털 기기 사용 시간 | |
| shopping_style | VARCHAR(100) | 쇼핑 스타일 | |
| purchase_decision_factors | TEXT[] | 구매 결정 요인 | DEFAULT [] |
| persona_created_at | TIMESTAMP | 생성일시 | DEFAULT NOW() |

**인덱스:**
- `idx_personas_persona_id` ON persona_id

---

#### 2. `analysis_results` - 분석 결과

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| analysis_id | SERIAL | 분석 ID | PRIMARY KEY |
| persona_id | VARCHAR(100) | 페르소나 ID | FOREIGN KEY → personas(persona_id) |
| analysis_result | TEXT | 분석 결과 텍스트 | |
| analysis_created_at | TIMESTAMP | 생성일시 | DEFAULT NOW() |

**인덱스:**
- `idx_analysis_results_persona_id` ON persona_id

---

#### 3. `search_queries` - 검색 쿼리

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| query_id | SERIAL | 쿼리 ID | PRIMARY KEY |
| analysis_id | INTEGER | 분석 ID | FOREIGN KEY → analysis_results(analysis_id) |
| search_query | TEXT | 검색 쿼리 텍스트 | |
| query_created_at | TIMESTAMP | 생성일시 | DEFAULT NOW() |

**인덱스:**
- `idx_search_queries_analysis_id` ON analysis_id

---

#### 4. `products` - 상품 정보

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| product_id | VARCHAR(100) | 상품 ID | PRIMARY KEY |
| vectordb_id | VARCHAR(100) | VectorDB ID (OpenSearch) | INDEX |
| product_name | VARCHAR(500) | 상품명 | NOT NULL |
| brand | VARCHAR(100) | 브랜드명 | INDEX |
| product_tag | VARCHAR(200) | 상품 태그 | |
| rating | NUMERIC(3,2) | 별점 (0~5) | |
| review_count | INTEGER | 리뷰 개수 | DEFAULT 0 |
| original_price | INTEGER | 원가 | |
| discount_rate | INTEGER | 할인율 | |
| sale_price | INTEGER | 판매가 | |
| skin_type | TEXT[] | 피부 타입 | DEFAULT [] |
| skin_concerns | TEXT[] | 피부 고민 | DEFAULT [] |
| preferred_colors | TEXT[] | 선호 색상 | DEFAULT [] |
| preferred_ingredients | TEXT[] | 선호 성분 | DEFAULT [] |
| avoided_ingredients | TEXT[] | 기피 성분 | DEFAULT [] |
| preferred_scents | TEXT[] | 선호 향 | DEFAULT [] |
| values | TEXT[] | 가치관 | DEFAULT [] |
| exclusive_product | VARCHAR(200) | 전용 제품 | |
| personal_color | TEXT[] | 퍼스널 컬러 | DEFAULT [] |
| skin_shades | INTEGER[] | 피부톤 번호 | DEFAULT [] |
| product_image_url | TEXT[] | 상품 이미지 URL | DEFAULT [] |
| product_page_url | TEXT | 상품 페이지 URL | |
| product_created_at | TIMESTAMP | 생성일시 | DEFAULT NOW() |

**인덱스:**
- `idx_products_vectordb_id` ON vectordb_id
- `idx_products_brand` ON brand

---

## 🚀 설치 및 실행

### 사전 요구사항

- Python 3.11+
- PostgreSQL 14+
- Git

### 1. 저장소 클론

```bash
git clone https://github.com/your-org/AI-INNOVATION-CHALLENGE-2026.git
cd AI-INNOVATION-CHALLENGE-2026/database
```

### 2. Python 환경 설정

#### 가상환경 생성 및 활성화

```bash
# 가상환경 생성
python -m venv venv

# 활성화
# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

#### 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env` 파일 생성:

```env
# PostgreSQL 설정
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_innovation_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password

# OpenAI API (Optional)
OPENAI_API_KEY=your_openai_api_key
```

### 4. 데이터베이스 연결 확인

```bash
python database.py
```

출력:
```
============================================================
Database Connection Test
============================================================
Host: localhost
Port: 5432
Database: ai_innovation_db
User: postgres
============================================================
[OK] Database connection successful: localhost:5432/ai_innovation_db

🎉 Database is ready!
```

### 5. 테이블 생성

PostgreSQL에서 직접 실행:

```bash
psql -U postgres -d ai_innovation_db -f init/01-create-tables.sql
```

### 6. FastAPI 서버 실행

```bash
python api_server.py
```

또는:

```bash
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

서버 시작:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [xxxxx]
INFO:     Application startup complete.
```

### 7. API 문서 확인

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## 📡 API 사용법

### API 엔드포인트 목록

| 메서드 | 엔드포인트 | 설명 |
|--------|------------|------|
| GET | `/` | API 루트 |
| GET | `/health` | 헬스 체크 |
| GET | `/api/health` | 데이터베이스 헬스 체크 |
| **Personas** |
| GET | `/api/personas` | 페르소나 목록 조회 |
| GET | `/api/personas/{persona_id}` | 특정 페르소나 조회 |
| POST | `/api/personas` | 페르소나 생성 |
| **Analysis Results** |
| GET | `/api/analysis-results` | 분석 결과 목록 조회 |
| GET | `/api/analysis-results/{analysis_id}` | 특정 분석 결과 조회 |
| POST | `/api/analysis-results` | 분석 결과 생성 |
| **Search Queries** |
| GET | `/api/search-queries` | 검색 쿼리 목록 조회 |
| POST | `/api/search-queries` | 검색 쿼리 생성 |
| **Products** |
| GET | `/api/products` | 상품 목록 조회 (필터: brand, product_name) |
| GET | `/api/products/{product_id}` | 특정 상품 상세 조회 |
| POST | `/api/products` | 상품 생성 |

### 예제 요청

#### 1. 헬스 체크

```bash
curl http://localhost:8000/health
```

응답:
```json
{
  "status": "healthy",
  "database": "connected",
  "schema_version": "2.0",
  "tables": {
    "products": 1523,
    "personas": 5,
    "analysis_results": 12,
    "search_queries": 8
  }
}
```

#### 2. 페르소나 생성

```bash
curl -X POST http://localhost:8000/api/personas \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "PERSONA_001",
    "name": "김지현",
    "gender": "여성",
    "age": 28,
    "occupation": "마케터",
    "skin_type": ["지성", "복합성"],
    "skin_concerns": ["모공", "칙칙함"],
    "personal_color": "웜톤",
    "preferred_ingredients": ["히알루론산", "나이아신아마이드"],
    "avoided_ingredients": ["알코올", "파라벤"]
  }'
```

#### 3. 분석 결과 생성

```bash
curl -X POST http://localhost:8000/api/analysis-results \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "PERSONA_001",
    "analysis_result": "지성 피부에 적합한 모공 케어 제품 추천"
  }'
```

#### 4. 상품 검색

```bash
# 브랜드로 검색
curl "http://localhost:8000/api/products?brand=설화수&limit=10"

# 상품명으로 검색
curl "http://localhost:8000/api/products?product_name=에센스&limit=10"
```

---

## 🔄 데이터 마이그레이션

### JSONL → SQL 변환

opensearch 폴더의 JSONL 데이터를 PostgreSQL에 삽입:

```bash
python jsonl_to_sql_new.py
```

실행 결과:
```
============================================================
JSONL to SQL Converter
Source: opensearch/product_data_251227.jsonl
============================================================
[INFO] Loading data from: product_data_251227.jsonl
[INFO] Loaded 1523 products
[INFO] Generating SQL...
[OK] Created: database/init/02-insert-products.sql
============================================================
[OK] SQL file generated successfully!
============================================================
```

생성된 SQL 파일 실행:
```bash
psql -U postgres -d ai_innovation_db -f init/02-insert-products.sql
```

---

## 📁 프로젝트 구조

```
database/
├── api_server.py              # FastAPI 메인 서버
├── api_endpoints.py           # POST 전용 엔드포인트
├── database.py                # DB 연결 및 세션 관리
├── models.py                  # SQLAlchemy ORM 모델
├── jsonl_to_sql_new.py        # JSONL → SQL 변환
├── requirements.txt           # Python 패키지 목록
├── .env                       # 환경 변수
├── .gitignore                 # Git 무시 파일
│
├── init/
│   ├── 01-create-tables.sql  # 테이블 생성 SQL
│   ├── 02-insert-products.sql # 상품 데이터 삽입 (생성됨)
│   └── table_type.md          # 테이블 스키마 정의
│
└── remove/                    # 구버전 파일 (Git 무시)
```

---

## 🔄 업데이트 로그

### 2025-12-31
- **PostgreSQL 스키마 재정의** (table_type.md 기준)
  - Brand 테이블 제거 → products.brand VARCHAR로 변경
  - 4개 테이블로 단순화 (personas, analysis_results, search_queries, products)
  - Primary Key: persona_id, product_id VARCHAR 타입으로 변경
- **SQLAlchemy 모델 재작성** (models.py)
- **FastAPI 엔드포인트 재구성** (api_server.py, api_endpoints.py)
- **JSONL 변환 스크립트 수정** (opensearch 데이터 기준)
- **requirements.txt 정리**

### TODO
- [ ] OpenSearch 벡터 검색 연동
- [ ] 추천 알고리즘 구현
- [ ] GPT-4 기반 상품 분석
- [ ] 프론트엔드 연동

---

## 📝 라이선스

이 프로젝트는 AI Innovation Challenge 2026을 위한 프로젝트입니다.
