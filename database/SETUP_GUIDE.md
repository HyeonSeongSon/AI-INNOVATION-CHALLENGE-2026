# Database Setup Guide

데이터베이스 초기화 및 데이터 색인 가이드

## 사전 요구사항

1. **PostgreSQL 실행**
   ```bash
   cd database
   docker compose up -d
   ```

   > **주의**: 기본 `docker-compose.yml`은 PostgreSQL을 `expose`만 하므로 **호스트에서 5432에 접속할 수
   > 없습니다.** 아래 스크립트를 호스트에서 실행하려면 dev 오버레이를 함께 올려야 합니다
   > (5432 포트 개방 + pgAdmin 5050 제공).
   >
   > ```bash
   > docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   > ```
   >
   > 오버레이 없이 진행하려면 컨테이너 안에서 실행하세요:
   > `docker compose exec api_server python scripts/setup_pipeline.py`

2. **환경변수 설정** (`.env` 파일 — `.env.example` 복사)
   ```bash
   POSTGRES_HOST=localhost
   POSTGRES_DB=ai_innovation_db
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_password
   INTERNAL_TOKEN=<openssl rand -hex 32>
   ```

   > `POSTGRES_PORT`는 dev 오버레이를 쓸 때만 필요합니다(`.env.example`에 주석 처리되어 있음).

3. **Python 패키지 설치** (호스트에서 실행할 경우)
   ```bash
   pip install -r requirements.txt
   ```

> **상품 데이터**: `database/data/product_data_for_db.jsonl`이 저장소에 포함되어 있어
> 별도의 사전 색인 없이 바로 적재할 수 있습니다. OpenSearch 색인은 이와 독립적으로
> [../opensearch/README.md](../opensearch/README.md)의 절차를 따르면 됩니다.

## 프로젝트 구조

```
database/
├── api_server.py                      ← FastAPI 진입점 (port 8020)
├── seed_products.py                   ← 상품 시드 (배포 환경에서 CI가 호출)
├── setup_db.py                        ← DB 초기화 헬퍼
├── alembic.ini                        ← Alembic 설정
│
├── core/                              ← DB 인프라
│   ├── database.py                    ← 연결 설정, get_db(), init_db()
│   ├── models.py                      ← SQLAlchemy ORM 모델
│   ├── pagination.py                  ← 페이지네이션 유틸
│   └── logging.py                     ← structlog 설정
│
├── routers/                           ← API 라우터
│   ├── api_endpoints.py               ← CRUD 엔드포인트 (/api/*)
│   ├── conversations_router.py        ← 대화 이력
│   ├── generated_messages_router.py   ← 생성 메시지
│   └── auth_utils.py                  ← 내부 토큰 검증
│
├── scripts/                           ← 데이터 삽입 / 유틸리티
│   ├── setup_pipeline.py              ← 테이블 생성 → 데이터 삽입 → 검증
│   ├── insert_personas.py
│   ├── insert_products_from_jsonl.py
│   └── jsonl_to_sql_new.py
│
├── migrations/                        ← Alembic 마이그레이션
│
├── init/                              ← PostgreSQL 초기화 SQL (01~07, 컨테이너 최초 기동 시 자동 적용)
│   ├── 01-create-tables.sql           ← personas/analysis_results/search_queries/products/
│   │                                     conversations/conversation_messages/generated_messages
│   ├── 02-auth-tables.sql             ← users/refresh_tokens
│   ├── 03-add-persona-user-id.sql
│   ├── 04-add-updated-at-trigger.sql
│   ├── 05-add-account-lockout.sql
│   ├── 06-add-rate-limits.sql         ← rate_limits
│   └── 07-add-persona-seq.sql
│
├── docker-compose.yml                 ← PostgreSQL + DB API
└── docker-compose.dev.yml             ← (오버레이) 5432 포트 개방 + pgAdmin 5050
```

> 페르소나 LLM 요약 생성(`persona_analyzer.py`)은 이 디렉터리가 아니라
> `backend/app/services/persona_analyzer.py`에 있습니다.

## 사용 방법

### 1. 기본 실행 (기존 데이터 유지)
```bash
cd database
python scripts/setup_pipeline.py
```

이 명령은:
- 데이터베이스 연결 확인
- 테이블이 없으면 생성 (있으면 스킵)
- 상품 데이터 삽입 (중복 제외)
- 데이터 검증

### 2. 전체 리셋 (기존 데이터 삭제 후 재생성)
```bash
cd database
python scripts/setup_pipeline.py --reset
```

**경고**: 이 명령은 모든 기존 데이터를 삭제합니다!

## 파이프라인 단계

### Step 1: 데이터베이스 연결 확인
- PostgreSQL 서버 연결 테스트
- 연결 실패 시 원인 안내

### Step 2: 테이블 생성

전체 **10개** 테이블이 생성됩니다. 아래에 상세 스키마를 적은 4개가 도메인 핵심 테이블이고,
나머지 6개는 [인증·대화·운영 테이블](#인증대화운영-테이블-6개)에 정리했습니다.

도메인 핵심 테이블 (4개):

#### 1. `personas` - 페르소나 정보
페르소나의 인구통계학적 정보, 피부 특성, 선호도 등을 저장

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| persona_id | VARCHAR(100) | 페르소나 고유 ID | PRIMARY KEY |
| name | VARCHAR(200) | 페르소나 이름 | NOT NULL |
| gender | VARCHAR(20) | 성별 | |
| age | INTEGER | 나이 | |
| occupation | VARCHAR(100) | 직업 | |
| skin_type | TEXT[] | 피부 타입 배열 | DEFAULT [] |
| skin_concerns | TEXT[] | 피부 고민 배열 | DEFAULT [] |
| personal_color | VARCHAR(50) | 퍼스널 컬러 | |
| shade_number | INTEGER | 셰이드 번호 | |
| preferred_colors | TEXT[] | 선호 색상 배열 | DEFAULT [] |
| preferred_ingredients | TEXT[] | 선호 성분 배열 | DEFAULT [] |
| avoided_ingredients | TEXT[] | 기피 성분 배열 | DEFAULT [] |
| preferred_scents | TEXT[] | 선호 향 배열 | DEFAULT [] |
| values | TEXT[] | 가치관 배열 | DEFAULT [] |
| skincare_routine | VARCHAR(100) | 스킨케어 루틴 | |
| main_environment | VARCHAR(100) | 주 활동 환경 | |
| preferred_texture | TEXT[] | 선호 제형 배열 | DEFAULT [] |
| pets | VARCHAR(50) | 반려동물 유무 | |
| avg_sleep_hours | INTEGER | 평균 수면 시간 | |
| stress_level | VARCHAR(50) | 스트레스 수준 | |
| digital_device_usage_time | INTEGER | 디지털 기기 사용 시간 | |
| shopping_style | VARCHAR(100) | 쇼핑 스타일 | |
| purchase_decision_factors | TEXT[] | 구매 결정 요인 배열 | DEFAULT [] |
| persona_created_at | TIMESTAMP | 생성 일시 | DEFAULT NOW() |

**인덱스:** `idx_personas_persona_id` ON persona_id

---

#### 2. `analysis_results` - 분석 결과
페르소나 기반 분석 결과 저장

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| analysis_id | SERIAL | 분석 결과 ID | PRIMARY KEY |
| persona_id | VARCHAR(100) | 페르소나 ID | FOREIGN KEY → personas(persona_id) |
| analysis_result | TEXT | 분석 결과 텍스트 | |
| analysis_created_at | TIMESTAMP | 생성 일시 | DEFAULT NOW() |

**인덱스:** `idx_analysis_results_persona_id` ON persona_id

---

#### 3. `search_queries` - 검색 쿼리
분석 결과 기반 검색 쿼리 저장

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| query_id | SERIAL | 쿼리 ID | PRIMARY KEY |
| analysis_id | INTEGER | 분석 결과 ID | FOREIGN KEY → analysis_results(analysis_id) |
| search_query | TEXT | 검색 쿼리 텍스트 | |
| query_created_at | TIMESTAMP | 생성 일시 | DEFAULT NOW() |

**인덱스:** `idx_search_queries_analysis_id` ON analysis_id

---

#### 4. `products` - 상품 정보
화장품 상품 정보 및 페르소나 매칭 속성 저장

| 컬럼명 | 타입 | 설명 | 제약조건 |
|--------|------|------|----------|
| product_id | VARCHAR(100) | 상품 고유 ID | PRIMARY KEY |
| vectordb_id | VARCHAR(100) | 벡터DB(OpenSearch) ID | INDEX |
| product_name | VARCHAR(500) | 상품명 | NOT NULL |
| brand | VARCHAR(100) | 브랜드명 | INDEX |
| product_tag | VARCHAR(200) | 상품 태그 | |
| rating | NUMERIC(3,2) | 별점 (0~5) | |
| review_count | INTEGER | 리뷰 개수 | DEFAULT 0 |
| original_price | INTEGER | 원가 | |
| discount_rate | INTEGER | 할인율 | |
| sale_price | INTEGER | 판매가 | |
| skin_type | TEXT[] | 피부 타입 배열 | DEFAULT [] |
| skin_concerns | TEXT[] | 피부 고민 배열 | DEFAULT [] |
| preferred_colors | TEXT[] | 선호 색상 배열 | DEFAULT [] |
| preferred_ingredients | TEXT[] | 선호 성분 배열 | DEFAULT [] |
| avoided_ingredients | TEXT[] | 기피 성분 배열 | DEFAULT [] |
| preferred_scents | TEXT[] | 선호 향 배열 | DEFAULT [] |
| values | TEXT[] | 가치관 배열 | DEFAULT [] |
| exclusive_product | VARCHAR(200) | 특정 대상 전용 제품 (임산부, 남성 등) | |
| personal_color | TEXT[] | 퍼스널 컬러 배열 | DEFAULT [] |
| skin_shades | INTEGER[] | 피부톤 번호 배열 | DEFAULT [] |
| product_image_url | TEXT[] | 상품 이미지 URL 배열 | DEFAULT [] |
| product_page_url | TEXT | 상품 페이지 URL | |
| product_created_at | TIMESTAMP | 생성 일시 | DEFAULT NOW() |

**인덱스:**
- `idx_products_vectordb_id` ON vectordb_id (벡터DB 연동용)
- `idx_products_brand` ON brand (브랜드별 검색 최적화)

#### 인증·대화·운영 테이블 (6개)

위 4개 외에 아래 6개가 함께 생성됩니다. 컬럼 정의는 각 SQL 파일을 참고하세요.

| 테이블 | 정의 위치 | 용도 |
|---|---|---|
| `conversations` | `init/01-create-tables.sql` | 대화 세션 (thread_id 단위) |
| `conversation_messages` | `init/01-create-tables.sql` | 대화 메시지 이력 |
| `generated_messages` | `init/01-create-tables.sql` | 생성된 CRM 메시지 + 품질 점수 |
| `users` | `init/02-auth-tables.sql` | 계정 (bcrypt 해시, role, 계정잠금 필드) |
| `refresh_tokens` | `init/02-auth-tables.sql` | refresh 토큰 회전·폐기 관리 |
| `rate_limits` | `init/06-add-rate-limits.sql` | PostgreSQL 기반 sliding-window Rate Limiter |

#### 스키마 변경은 Alembic으로 관리합니다

`init/*.sql`은 **컨테이너 최초 기동 시 빈 데이터 디렉터리에 한 번만** 적용됩니다
(`/docker-entrypoint-initdb.d`). 이후의 스키마 변경은 Alembic이 담당합니다.

```bash
# DB API 컨테이너는 기동 시 자동으로 최신 리비전까지 적용한다
#   command: sh -c "alembic upgrade head && uvicorn api_server:app ..."

# 수동 적용 / 리비전 생성
alembic upgrade head
alembic revision --autogenerate -m "설명"
alembic current          # 현재 리비전 확인
```

> 이미 데이터가 있는 볼륨에 `init/*.sql`은 재적용되지 않으므로, 운영 중 스키마를 바꿀 때는
> 반드시 Alembic 리비전을 추가해야 합니다. `scripts/setup_pipeline.py`도 `alembic.ini`를
> 참조합니다.

### Step 3: 상품 데이터 삽입
- `data/product_data_for_db.jsonl` 파일에서 데이터 로드
- PostgreSQL에 bulk insert
- 100개씩 배치 커밋
- 진행 상황 실시간 출력

### Step 4: 데이터 검증
- 총 상품 개수 확인
- 브랜드별 상품 통계
- 샘플 데이터 출력

## 출력 예시

```
================================================================================
DATABASE SETUP PIPELINE
================================================================================
Database: ai_innovation_db
Host: localhost:5432
Reset mode: False
================================================================================

[STEP 1] Checking database connection...
--------------------------------------------------------------------------------
✅ Connection successful

[STEP 2] Creating database tables...
--------------------------------------------------------------------------------
Creating tables...

Created tables (4):
  - analysis_results
  - personas
  - products
  - search_queries
✅ Tables created successfully

[STEP 3] Inserting product data...
--------------------------------------------------------------------------------
Loaded 1500 products from JSONL
  Progress: 100/1500 products inserted
  Progress: 200/1500 products inserted
  ...
  Progress: 1500/1500 products inserted

Insert summary:
  - Success: 1500
  - Errors: 0
  - Total: 1500
✅ Product data inserted

[STEP 4] Validating data...
--------------------------------------------------------------------------------
Total products in database: 1500

Top 10 brands by product count:
  - 라네즈: 150 products
  - 설화수: 120 products
  - 이니스프리: 100 products
  ...

Sample products:
  - [PROD001] 라네즈 워터뱅크 에센스 (라네즈)
  - [PROD002] 설화수 자음생크림 (설화수)
  - [PROD003] 이니스프리 그린티 세럼 (이니스프리)
✅ Validation completed

================================================================================
✅ PIPELINE COMPLETED SUCCESSFULLY!
================================================================================
```

## 문제 해결

### 1. "Database connection failed"
```
원인: PostgreSQL 서버가 실행되지 않았거나 호스트에서 5432에 접근할 수 없음
해결:
  - docker compose ps 로 postgres 컨테이너 상태 확인
  - 호스트에서 실행 중이라면 dev 오버레이가 올라와 있는지 확인
      docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
    (기본 compose는 5432를 expose만 하므로 호스트에서 접근 불가)
  - .env 파일의 데이터베이스 정보 확인
```

### 2. "상품 데이터 파일을 찾을 수 없습니다" (Product data file not found)
```
원인: database/data/product_data_for_db.jsonl 을 찾지 못함
해결:
  1. 파일 존재 확인 (저장소에 포함되어 있음)
       ls -l database/data/product_data_for_db.jsonl

  2. 스크립트를 database/ 디렉터리에서 실행했는지 확인 (경로가 상대 기준)

  3. 컨테이너 안에서 실행한다면 해당 경로가 이미지에 포함됐는지 확인
```

### 3. "Permission denied"
```
원인: 데이터베이스 사용자 권한 부족
해결:
  - PostgreSQL 사용자에게 CREATE, INSERT 권한 부여
  - 또는 관리자 계정으로 실행
```

## 개별 스크립트 실행

필요에 따라 개별 스크립트를 직접 실행할 수도 있습니다:

### 데이터베이스 연결 테스트만
```bash
cd database
python core/database.py
```

### 테이블만 생성
```python
from core.database import init_db
init_db()
```

### 상품 데이터만 삽입
```bash
cd database
python scripts/insert_products_from_jsonl.py
```

### 페르소나 데이터만 삽입
```bash
cd database
python scripts/insert_personas.py
```

## 다음 단계

데이터베이스 초기화 후:

1. **API 서버 실행**
   ```bash
   cd database
   python api_server.py
   ```
   → 포트 8020에서 데이터베이스 API 실행

2. **API 테스트**
   ```bash
   curl http://localhost:8020/api/products/filter
   ```
