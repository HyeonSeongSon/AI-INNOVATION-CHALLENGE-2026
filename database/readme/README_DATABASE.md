# AI Innovation Challenge 2026 - Database Guide

PostgreSQL 데이터베이스 설계 및 사용 가이드

## 📊 데이터베이스 ERD

```
┌──────────────┐
│   brands     │
├──────────────┤
│ id (PK)      │
│ name         │◄────────┐
│ brand_url    │         │
│ tone_desc... │         │
│ ...          │         │
└──────────────┘         │
                         │ 1:N
                         │
┌──────────────┐         │
│  products    │         │
├──────────────┤         │
│ id (PK)      │         │
│ brand_id (FK)├─────────┘
│ product_code │
│ product_name │
│ category     │
│ tags (JSONB) │
│ ...          │
└──────┬───────┘
       │
       │ N:M (through product_personas)
       │
┌──────▼───────┐         ┌──────────────┐
│product_      │         │  personas    │
│personas      │         ├──────────────┤
├──────────────┤         │ id (PK)      │
│ id (PK)      │    ┌───►│ persona_key  │
│ product_id   │────┘    │ name         │
│ persona_id   │────┐    │ age_group    │
│ relevance_   │    │    │ keywords[]   │
│   score      │    │    │ metadata     │
└──────────────┘    │    └──────┬───────┘
                    │           │
                    └───────────┘
                                │ 1:N
                                │
                    ┌───────────▼──────────┐
                    │ persona_analysis_    │
                    │ results              │
                    ├──────────────────────┤
                    │ id (PK)              │
                    │ persona_id (FK)      │
                    │ product_id (FK)      │
                    │ analysis_type        │
                    │ analysis_result      │
                    │ generated_message    │
                    └──────┬───────────────┘
                           │ 1:N
                           │
                    ┌──────▼───────────┐
                    │ persona_         │
                    │ solutions        │
                    ├──────────────────┤
                    │ id (PK)          │
                    │ analysis_result_ │
                    │   id (FK)        │
                    │ solution_type    │
                    │ title            │
                    │ recommended_     │
                    │   products       │
                    └──────────────────┘
```

## 📋 테이블 설명

### 1. brands (브랜드 정보)
브랜드의 기본 정보와 톤&매너를 저장합니다.

**주요 컬럼:**
- `name`: 브랜드명 (UNIQUE)
- `tone_description`: 브랜드 톤 설명
- `target_audience`: 타겟 고객층 (JSONB)
- `core_keywords`: 핵심 키워드 (TEXT[])

### 2. products (상품 정보)
화장품 상품의 상세 정보를 저장합니다.

**주요 컬럼:**
- `brand_id`: 브랜드 외래키
- `product_code`: 상품 코드
- `category`: 카테고리 (스킨케어, 메이크업 등)
- `tags`: 상품 태그 (JSONB)
  - `category_tags`: 카테고리 태그
  - `ingredient_tags`: 성분 태그
  - `concern_tags`: 고민 해결 태그
  - `feature_tags`: 특징 태그
- `buyer_statistics`: 구매자 통계 (JSONB)

### 3. personas (페르소나 정보)
고객 페르소나 정의를 저장합니다.

**주요 컬럼:**
- `persona_key`: 페르소나 식별 키 (UNIQUE)
- `age_group`: 연령대
- `income_level`: 소득 수준
- `skin_concerns`: 피부 고민 (TEXT[])
- `decision_factors`: 의사결정 요인 (TEXT[])

기본 정보
성별: 여성, 남성, 기타(동물?)

피부 스펙
피부 타입 (8종): 건성, 중성, 복합성, 지성, 민감성, 악건성, 트러블성, 수분부족지성

퍼스널 컬러 (7종): 웜톤, 봄웜톤, 가을웜톤, 쿨톤, 여름쿨톤, 겨울쿨톤, 뉴트럴톤

베이스 호수 (6종): 13호, 17호, 19호, 21호, 23호, 25호

피부 고민
고민 키워드 (17종): 잡티, 미백, 주름, 각질, 여드름, 블랙헤드, 피지과다, 아토피, 민감성, 다크서클, 기미, 홍조, 유수분밸런스, 탄력, 트러블자국, 비듬, 탈모

메이크업 취향
선호 포인트 컬러: 레드, 핑크, 코랄, 오렌지, 베이지, 브라운

성분 및 향
선호 성분 (Positive): 히알루론산, 나이아신아마이드, 레티놀, 비타민C, 펩타이드, 시카, 티트리, 세라마이드, 콜라겐, 알부틴

기피 성분 (Negative): 파라벤, 알코올,인공향료, 인공색소, 미네랄오일, 실리콘, SLS/SLES, 합성방부제
(GPT왈:기피 성분은 보통 'FREE'를 붙여 태깅하거나 별도 필드로 관리합니다)

선호 향: 무향, 플로럴, 시트러스, 허브, 우디, 머스크

가치관
특수 조건: 천연/유기농, 비건/크루얼티프리, 친환경패키징, 임산부/수유부

### 4. product_personas (상품-페르소나 매핑)
상품과 페르소나 간의 연관성을 저장합니다.

**주요 컬럼:**
- `relevance_score`: 연관도 점수 (0.0 ~ 1.0)
- `matched_attributes`: 매칭된 속성 정보 (JSONB)

### 5. persona_analysis_results (페르소나 분석 결과)
페르소나별 분석 결과를 저장합니다.

**주요 컬럼:**
- `analysis_type`: 분석 유형 (recommendation, trend_analysis 등)
- `analysis_result`: 분석 결과 (JSONB)
- `confidence_score`: 신뢰도 점수
- `generated_message`: 생성된 메시지

### 6. persona_solutions (페르소나 솔루션)
페르소나별 추천 솔루션을 저장합니다.

**주요 컬럼:**
- `solution_type`: 솔루션 유형 (product_bundle, skincare_routine 등)
- `recommended_products`: 추천 상품 리스트 (JSONB)
- `effectiveness_score`: 효과 점수

### 7. user_profiles (사용자 프로필) [NEW]
프론트엔드에서 수집한 개별 사용자의 프로필 정보를 저장합니다.
5개의 기본 페르소나가 아닌, 각 사용자별 맞춤 추천을 위한 테이블입니다.

**주요 컬럼:**
- `user_id`: 로그인 사용자 ID (외부 시스템)
- `session_id`: 비로그인 사용자 세션 ID
- `gender`: 성별
- `skin_type`: 피부 타입 (단일 선택)
- `personal_color`: 퍼스널컬러
- `base_shade`: 베이스 호수
- `skin_concerns`: 피부 고민 (최대 3개)
- `preferred_ingredients`: 선호 성분
- `avoided_ingredients`: 기피 성분
- `preferred_scents`: 선호 향
- `special_conditions`: 특수 조건 (비건, 유기농 등)
- `age_group`: 연령대
- `budget_range`: 예산 범위

**사용 시나리오:**
프론트엔드에서 사용자로부터 정보를 수집하면, 해당 정보를 user_profiles 테이블에 저장하고,
이를 기반으로 개인화된 상품 추천을 제공합니다.

### 8. user_recommendations (사용자 맞춤 추천) [NEW]
개별 사용자에게 제공된 맞춤 추천 이력을 저장합니다.

**주요 컬럼:**
- `user_profile_id`: 사용자 프로필 외래키
- `product_id`: 추천된 상품 외래키
- `relevance_score`: 연관도 점수 (0.0 ~ 1.0)
- `matched_attributes`: 매칭된 속성 (JSONB)
- `matching_reasons`: 추천 이유 (한글 설명)
- `recommendation_type`: 추천 타입 (skin_concern, ingredient, personal_color 등)
- `user_clicked`: 클릭 여부
- `user_purchased`: 구매 여부
- `user_rating`: 사용자 평가 (1-5점)

## 🚀 시작하기

### 1. 데이터베이스 시작

```bash
cd database
docker-compose up -d
```

### 2. 연결 확인

```bash
python database.py
```

### 3. 초기 데이터 로드

Docker Compose로 시작하면 자동으로 초기 데이터가 로드됩니다:
- `init/01-create-tables.sql` - 테이블 생성
- `init/02-seed-initial-data.sql` - 페르소나 및 브랜드 초기 데이터

### 4. 크롤링 데이터 마이그레이션

```bash
python migrate_data.py
```

## 💻 Python 사용 예제

### 데이터베이스 연결

```python
from database import get_db, check_connection
from models import Product, Brand, Persona

# 연결 확인
if check_connection():
    print("✅ 연결 성공")

# 세션 사용
with next(get_db()) as db:
    # 쿼리 실행
    products = db.query(Product).all()
```

### 상품 조회

```python
from database import get_db
from models import Product, Brand

db = next(get_db())

# 브랜드별 상품 조회
products = db.query(Product).join(Brand).filter(
    Brand.name == "라네즈"
).all()

for product in products:
    print(f"{product.product_name} - {product.price}원")
```

### 페르소나별 추천 상품 조회

```python
from sqlalchemy.orm import joinedload
from models import Persona, ProductPersona, Product

db = next(get_db())

# 페르소나 로드 with eager loading
persona = db.query(Persona).filter(
    Persona.persona_key == "trendy_beauty_20s"
).options(
    joinedload(Persona.product_personas).joinedload(ProductPersona.product)
).first()

# 연관도 높은 순으로 정렬
product_personas = sorted(
    persona.product_personas,
    key=lambda x: x.relevance_score,
    reverse=True
)

# 상위 10개 추천 상품
for pp in product_personas[:10]:
    print(f"{pp.product.product_name} - 연관도: {pp.relevance_score}")
```

### 카테고리별 필터링

```python
# JSONB 필드 쿼리
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB

# 특정 성분 포함 상품 검색
products = db.query(Product).filter(
    Product.tags['ingredient_tags'].astext.contains('히알루론산')
).all()

# 특정 피부 고민 해결 상품 검색
products = db.query(Product).filter(
    Product.tags['concern_tags'].astext.contains('주름개선')
).all()
```

### 새 상품 추가

```python
from models import Product

db = next(get_db())

new_product = Product(
    brand_id=1,
    product_code="PRD001",
    product_name="수분 크림",
    category="스킨케어",
    price=35000,
    tags={
        "category_tags": ["스킨케어-크림"],
        "ingredient_tags": ["히알루론산", "세라마이드"],
        "concern_tags": ["보습", "건조"]
    }
)

db.add(new_product)
db.commit()
```

### 페르소나 분석 결과 저장

```python
from models import PersonaAnalysisResult, PersonaSolution

# 분석 결과 생성
analysis = PersonaAnalysisResult(
    persona_id=1,
    product_id=10,
    analysis_type="recommendation",
    analysis_result={
        "matching_reasons": ["연령대 적합", "피부 타입 매칭"],
        "key_benefits": ["보습 효과", "간편한 사용"]
    },
    confidence_score=0.85,
    generated_message="바쁜 워킹맘을 위한 5분 완성 수분 크림"
)
db.add(analysis)
db.flush()

# 솔루션 추가
solution = PersonaSolution(
    analysis_result_id=analysis.id,
    solution_type="product_bundle",
    title="5분 완성 모닝 루틴",
    description="아침 시간이 부족한 당신을 위한 간편 케어 세트",
    recommended_products=[
        {"product_id": 10, "order": 1},
        {"product_id": 15, "order": 2}
    ],
    priority=1,
    effectiveness_score=0.9
)
db.add(solution)
db.commit()
```

### 사용자 프로필 생성 및 맞춤 추천

```python
from models import UserProfile, UserRecommendation, Product

# 1. 프론트엔드에서 받은 사용자 정보로 프로필 생성
user_profile = UserProfile(
    user_id="user_12345",  # 로그인 사용자
    gender="여성",
    skin_type="복합성",
    personal_color="쿨톤",
    base_shade="21호",
    skin_concerns=["주름", "탄력", "미백"],
    preferred_ingredients=["레티놀", "나이아신아마이드", "비타민C"],
    avoided_ingredients=["파라벤", "알코올"],
    preferred_scents=["무향", "플로럴"],
    special_conditions=["비건/크루얼티프리"],
    age_group="30대",
    budget_range="중상"
)

db.add(user_profile)
db.commit()

# 2. 사용자 프로필 기반 상품 추천
# 예: 선호 성분이 포함되고, 기피 성분이 없는 상품 찾기
from sqlalchemy import and_, or_

recommended_products = db.query(Product).filter(
    # 선호 성분 중 하나라도 포함
    or_(*[
        Product.tags['ingredient_tags'].astext.contains(ingredient)
        for ingredient in user_profile.preferred_ingredients
    ]),
    # 기피 성분이 없는 상품
    ~or_(*[
        Product.tags['ingredient_tags'].astext.contains(ingredient)
        for ingredient in user_profile.avoided_ingredients
    ])
).limit(20).all()

# 3. 추천 결과 저장
for product in recommended_products:
    # 추천 점수 계산 (간단한 예시)
    relevance_score = 0.75

    recommendation = UserRecommendation(
        user_profile_id=user_profile.id,
        product_id=product.id,
        relevance_score=relevance_score,
        matched_attributes={
            "matched_ingredients": ["레티놀", "나이아신아마이드"],
            "skin_type_match": True
        },
        matching_reasons=[
            "선호하시는 레티놀 성분이 포함되어 있습니다",
            "복합성 피부에 적합한 제품입니다",
            "비건 인증 제품입니다"
        ],
        recommendation_type="ingredient"
    )
    db.add(recommendation)

db.commit()

# 4. 비로그인 사용자 (세션 기반)
session_profile = UserProfile(
    session_id="session_abc123",  # 세션 ID
    skin_type="민감성",
    skin_concerns=["홍조", "민감성"],
    avoided_ingredients=["파라벤", "알코올", "인공향료"]
)
db.add(session_profile)
db.commit()

# 5. 사용자 반응 기록
recommendation = db.query(UserRecommendation).filter(
    UserRecommendation.user_profile_id == user_profile.id,
    UserRecommendation.product_id == 123
).first()

# 클릭 기록
recommendation.user_clicked = True

# 구매 기록
recommendation.user_purchased = True

# 평가 기록
recommendation.user_rating = 5

db.commit()
```

### 사용자별 추천 상품 조회

```python
from sqlalchemy.orm import joinedload

# 특정 사용자의 추천 상품 조회 (연관도 높은 순)
user_recommendations = db.query(UserRecommendation).filter(
    UserRecommendation.user_profile_id == user_profile.id
).options(
    joinedload(UserRecommendation.product).joinedload(Product.brand)
).order_by(
    UserRecommendation.relevance_score.desc()
).limit(10).all()

for rec in user_recommendations:
    print(f"상품: {rec.product.product_name}")
    print(f"브랜드: {rec.product.brand.name}")
    print(f"연관도: {rec.relevance_score}")
    print(f"추천 이유: {', '.join(rec.matching_reasons)}")
    print("---")
```

## 🔍 유용한 쿼리

### 브랜드별 상품 수 통계

```sql
SELECT b.name, COUNT(p.id) as product_count
FROM brands b
LEFT JOIN products p ON b.id = p.brand_id
GROUP BY b.id, b.name
ORDER BY product_count DESC;
```

### 페르소나별 추천 상품 수

```sql
SELECT
    pe.name,
    pe.persona_key,
    COUNT(pp.id) as matched_products,
    AVG(pp.relevance_score) as avg_relevance
FROM personas pe
LEFT JOIN product_personas pp ON pe.id = pp.persona_id
GROUP BY pe.id, pe.name, pe.persona_key
ORDER BY matched_products DESC;
```

### 카테고리별 평균 가격

```sql
SELECT
    category,
    COUNT(*) as product_count,
    ROUND(AVG(price), 2) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price
FROM products
WHERE price IS NOT NULL
GROUP BY category
ORDER BY avg_price DESC;
```

### 특정 성분 포함 상품 검색

```sql
SELECT
    product_name,
    tags->'ingredient_tags' as ingredients
FROM products
WHERE tags->'ingredient_tags' @> '["히알루론산"]'::jsonb;
```

## 📝 환경 변수 설정

`.env` 파일에 다음 변수가 설정되어 있는지 확인하세요:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_innovation_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
```

## 🔧 유지보수

### 백업

```bash
# 데이터베이스 백업
docker-compose exec postgres pg_dump -U postgres ai_innovation_db > backup.sql

# 압축 백업
docker-compose exec postgres pg_dump -U postgres ai_innovation_db | gzip > backup.sql.gz
```

### 복원

```bash
# SQL 파일에서 복원
docker-compose exec -T postgres psql -U postgres ai_innovation_db < backup.sql

# 압축 파일에서 복원
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U postgres ai_innovation_db
```

### 테이블 재생성

```python
from database import drop_all_tables, init_db

# ⚠️  주의: 모든 데이터가 삭제됩니다!
drop_all_tables()
init_db()
```

## 📚 추가 리소스

- [SQLAlchemy 공식 문서](https://docs.sqlalchemy.org/)
- [PostgreSQL JSONB 타입](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL 인덱싱 전략](https://www.postgresql.org/docs/current/indexes.html)

## 🐛 문제 해결

### 연결 오류

```bash
# PostgreSQL 컨테이너 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs postgres

# 재시작
docker-compose restart postgres
```

### 마이그레이션 오류

```python
# 데이터베이스 연결 테스트
python database.py

# 테이블 확인
psql -h localhost -U postgres -d ai_innovation_db -c "\dt"
```

## 📞 지원

문제가 발생하면 다음을 확인하세요:
1. PostgreSQL 컨테이너가 실행 중인지 확인
2. `.env` 파일 설정이 올바른지 확인
3. 네트워크 연결 확인
4. 로그 파일 검토
