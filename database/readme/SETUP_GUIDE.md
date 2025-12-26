# 데이터베이스 구성 및 단계별 설정 가이드

## 📊 최종 데이터베이스 구조

### 테이블 구성 (총 6개)

```
1. brands (브랜드 정보)
   - 브랜드 기본 정보, 톤앤매너, 타겟 고객

2. products (상품 정보)
   - 상품 기본 정보: 상품명, 가격, 카테고리
   - generated_document: GPT가 생성한 구조화된 상품 설명 문서
   - tags: 상품 태그 (성분/고민/특징)
   - buyer_statistics: 구매자 통계

3. personas (페르소나 정보)
   - persona_categories.json 기반 필드 구조
   - 프론트엔드에서 페르소나 정보를 받아서 추가
   - 초기 데이터 없음 (빈 테이블)

4. product_personas (상품-페르소나 매핑)
   - 상품과 페르소나 간 다대다 관계
   - relevance_score: 연관도 점수
   - matched_attributes: 매칭 속성

5. persona_analysis_results (페르소나 분석 결과)
   - 페르소나별 분석 데이터
   - analysis_type: 분석 유형
   - analysis_result: 분석 결과 (JSONB)

6. persona_solutions (페르소나 솔루션)
   - 페르소나별 추천 솔루션
   - solution_type: 솔루션 유형
   - recommended_products: 추천 상품 목록
```

### SQL 파일 구성

```
database/init/
├── 01-create-tables.sql              # 6개 테이블 생성 (personas는 persona_categories.json 구조)
├── 02-seed-initial-data.sql          # 브랜드만 삽입 (페르소나는 빈 상태)
├── 04-insert-brands.sql              # 크롤링 데이터에서 브랜드 추가 (자동생성)
├── 05-insert-products.sql            # 크롤링 데이터에서 상품 추가 (자동생성)
└── 06-insert-product-personas.sql    # 상품-페르소나 매핑 (자동생성)
```

---

## 🚀 단계별 실행 가이드

### 1단계: Docker 데이터베이스 시작

```bash
cd AI-INNOVATION-CHALLENGE-2026-hs_branch/database
docker-compose up -d
```

**자동 실행:**
- `01-create-tables.sql` - 6개 테이블 생성
  - personas 테이블은 persona_categories.json 필드 구조로 생성됨
  - 초기 데이터 없음 (빈 테이블)
- `02-seed-initial-data.sql` - 브랜드 5개만 삽입

**확인:**
- PostgreSQL: `localhost:5432`
- pgAdmin: `http://localhost:5050`

---

### 2단계: 크롤링 데이터를 SQL로 변환

```bash
cd AI-INNOVATION-CHALLENGE-2026-hs_branch/database
python jsonl_to_sql.py
```

**필요한 파일:**
- `AI-INNOVATION-CHALLENGE-2026/data/crawling_result/*.jsonl`

**생성되는 파일:**
- `init/04-insert-brands.sql` - 브랜드 INSERT
- `init/05-insert-products.sql` - 상품 INSERT
- `init/06-insert-product-personas.sql` - 매핑 INSERT

---

### 3단계: 상품 데이터 임포트

```bash
# 1. 브랜드 임포트
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/04-insert-brands.sql

# 2. 상품 임포트
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/05-insert-products.sql

# 3. 상품-페르소나 매핑 임포트
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/06-insert-product-personas.sql
```

---

### 4단계: 데이터베이스 연결 테스트

```bash
cd AI-INNOVATION-CHALLENGE-2026-hs_branch/database
python test_connection.py
```

---

## 📋 Personas 테이블 구조

### persona_categories.json 기반 필드

```sql
-- 1. 기본 정보
gender              VARCHAR(20)      -- 성별 (여성, 남성, 무관)
age_group           VARCHAR(50)      -- 연령대

-- 2. 피부 스펙
skin_types          TEXT[]           -- 피부타입 배열 (건성, 중성, 복합성, 지성, 민감성 등)
personal_color      VARCHAR(50)      -- 퍼스널컬러 (웜톤, 쿨톤, 뉴트럴톤 등)
base_shade          VARCHAR(10)      -- 베이스 호수 (13호, 17호, 19호, 21호, 23호, 25호)

-- 3. 피부 고민 (최대 3개)
skin_concerns       TEXT[]           -- 잡티, 미백, 주름, 각질, 여드름 등

-- 4. 메이크업 선호
preferred_point_colors TEXT[]        -- 레드, 핑크, 코랄, 오렌지, 베이지, 브라운

-- 5. 성분 선호
preferred_ingredients  TEXT[]        -- 히알루론산, 나이아신아마이드, 레티놀 등
avoided_ingredients    TEXT[]        -- 파라벤, 알코올, 인공향료 등
preferred_scents       TEXT[]        -- 무향, 플로럴, 시트러스, 허브 등

-- 6. 가치관
special_conditions     TEXT[]        -- 천연/유기농, 비건/크루얼티프리 등

-- 추가
budget_range          VARCHAR(50)    -- 예산 범위
metadata              JSONB          -- 추가 메타데이터
```

---

## 💻 프론트엔드에서 페르소나 추가하기

### Python 예제

```python
from database import get_db
from models import Persona

db = next(get_db())

# 프론트엔드에서 받은 페르소나 정보
persona_data = {
    "persona_key": "user_persona_001",
    "name": "30대 건성 피부 직장인",
    "description": "건성 피부 고민이 있는 30대 여성",
    "gender": "여성",
    "age_group": "30대",
    "skin_types": ["건성", "민감성"],
    "personal_color": "웜톤",
    "base_shade": "21호",
    "skin_concerns": ["건조", "주름", "탄력"],
    "preferred_point_colors": ["베이지", "브라운"],
    "preferred_ingredients": ["히알루론산", "세라마이드", "레티놀"],
    "avoided_ingredients": ["파라벤", "알코올"],
    "preferred_scents": ["무향", "플로럴"],
    "special_conditions": ["천연/유기농"],
    "budget_range": "중"
}

# 페르소나 생성
persona = Persona(**persona_data)
db.add(persona)
db.commit()

print(f"페르소나 추가 완료: {persona.name}")
```

### FastAPI 엔드포인트 예제

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from models import Persona

app = FastAPI()

class PersonaCreate(BaseModel):
    persona_key: str
    name: str
    description: Optional[str] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    skin_types: List[str] = []
    personal_color: Optional[str] = None
    base_shade: Optional[str] = None
    skin_concerns: List[str] = []
    preferred_point_colors: List[str] = []
    preferred_ingredients: List[str] = []
    avoided_ingredients: List[str] = []
    preferred_scents: List[str] = []
    special_conditions: List[str] = []
    budget_range: Optional[str] = None

@app.post("/api/personas")
def create_persona(persona_data: PersonaCreate):
    """
    프론트엔드에서 페르소나 정보를 받아서 추가
    """
    db = next(get_db())

    # 기존 페르소나 확인
    existing = db.query(Persona).filter(
        Persona.persona_key == persona_data.persona_key
    ).first()

    if existing:
        return {"error": "Persona already exists"}

    # 새 페르소나 생성
    persona = Persona(**persona_data.dict())
    db.add(persona)
    db.commit()
    db.refresh(persona)

    return {
        "id": persona.id,
        "persona_key": persona.persona_key,
        "name": persona.name,
        "message": "Persona created successfully"
    }

@app.get("/api/personas")
def get_personas():
    """
    모든 페르소나 조회
    """
    db = next(get_db())
    personas = db.query(Persona).all()

    return {
        "total": len(personas),
        "personas": [
            {
                "id": p.id,
                "persona_key": p.persona_key,
                "name": p.name,
                "gender": p.gender,
                "age_group": p.age_group,
                "skin_types": p.skin_types,
                "skin_concerns": p.skin_concerns
            }
            for p in personas
        ]
    }

@app.get("/api/personas/{persona_key}")
def get_persona(persona_key: str):
    """
    특정 페르소나 조회
    """
    db = next(get_db())
    persona = db.query(Persona).filter(
        Persona.persona_key == persona_key
    ).first()

    if not persona:
        return {"error": "Persona not found"}

    return {
        "id": persona.id,
        "persona_key": persona.persona_key,
        "name": persona.name,
        "description": persona.description,
        "gender": persona.gender,
        "age_group": persona.age_group,
        "skin_types": persona.skin_types,
        "personal_color": persona.personal_color,
        "base_shade": persona.base_shade,
        "skin_concerns": persona.skin_concerns,
        "preferred_point_colors": persona.preferred_point_colors,
        "preferred_ingredients": persona.preferred_ingredients,
        "avoided_ingredients": persona.avoided_ingredients,
        "preferred_scents": persona.preferred_scents,
        "special_conditions": persona.special_conditions,
        "budget_range": persona.budget_range
    }
```

---

## 🔍 데이터 확인 쿼리

### 페르소나 목록 조회

```sql
SELECT
    persona_key,
    name,
    gender,
    age_group,
    skin_types,
    skin_concerns,
    preferred_ingredients
FROM personas
ORDER BY created_at DESC;
```

### 페르소나별 매칭 상품 수

```sql
SELECT
    p.name AS persona_name,
    COUNT(pp.id) AS matched_products,
    ROUND(AVG(pp.relevance_score)::numeric, 4) AS avg_relevance
FROM personas p
LEFT JOIN product_personas pp ON p.id = pp.persona_id
GROUP BY p.name
ORDER BY matched_products DESC;
```

### 특정 페르소나에 맞는 상품 조회

```sql
SELECT
    pr.product_name,
    pr.category,
    pr.price,
    pp.relevance_score,
    b.name AS brand_name
FROM product_personas pp
JOIN personas p ON pp.persona_id = p.id
JOIN products pr ON pp.product_id = pr.id
JOIN brands b ON pr.brand_id = b.id
WHERE p.persona_key = 'user_persona_001'
ORDER BY pp.relevance_score DESC
LIMIT 20;
```

---

## 📁 핵심 파일

### 데이터베이스 설정
- `database/docker-compose.yml` - Docker 설정
- `database/.env` - 환경변수
- `database/database.py` - DB 연결
- `database/models.py` - ORM 모델 (6개 클래스)

### SQL 스크립트
- `database/init/01-create-tables.sql` - 테이블 생성
- `database/init/02-seed-initial-data.sql` - 브랜드만 삽입

### 도구
- `database/jsonl_to_sql.py` - JSONL → SQL 변환
- `database/test_connection.py` - 연결 테스트

---

## ✅ 현재 상태 요약

### 완료
- ✅ 6개 테이블 스키마 (personas는 persona_categories.json 구조)
- ✅ Docker Compose 설정
- ✅ SQLAlchemy ORM 모델
- ✅ JSONL → SQL 변환 스크립트
- ✅ 브랜드 초기 데이터 (5개)

### 초기 상태
- ⭕ personas 테이블: 빈 상태 (프론트엔드에서 추가 대기)
- ⭕ products 테이블: 빈 상태 (크롤링 데이터 임포트 대기)
- ⭕ product_personas 테이블: 빈 상태 (매핑 데이터 대기)

---

## 🎯 작동 흐름

```
1. Docker 시작
   ↓
2. 테이블 자동 생성 (personas는 빈 상태)
   ↓
3. 브랜드 5개 자동 삽입
   ↓
4. [선택] 크롤링 데이터 → SQL 변환 → 상품 임포트
   ↓
5. 프론트엔드에서 페르소나 정보 전송
   ↓
6. API로 personas 테이블에 추가
   ↓
7. 페르소나별 상품 추천 알고리즘 실행
   ↓
8. product_personas 테이블에 매핑 저장
```

---

## 다음 단계

```bash
# 1. Docker 시작
docker-compose up -d

# 2. 연결 테스트
python test_connection.py

# 3. 크롤링 데이터 있는 경우
python jsonl_to_sql.py
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/04-insert-brands.sql
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/05-insert-products.sql
docker-compose exec -T postgres psql -U postgres ai_innovation_db < init/06-insert-product-personas.sql

# 4. API 서버 구현하여 프론트엔드와 연동
# - POST /api/personas - 페르소나 추가
# - GET /api/personas - 페르소나 목록
# - GET /api/personas/{key}/products - 페르소나별 추천 상품
```
