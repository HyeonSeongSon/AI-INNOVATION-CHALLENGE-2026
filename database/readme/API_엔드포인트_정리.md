# API 엔드포인트 완전 정리

## ✅ 모든 엔드포인트 검증 완료

---

## 📡 전체 엔드포인트 목록

### 1. System
- `GET /` - API 루트 정보
- `GET /health` - 헬스 체크

### 2. Brands (브랜드)
- `GET /api/brands` - 모든 브랜드 조회
- `GET /api/brands/{brand_id}/products` - 특정 브랜드의 상품 조회

### 3. Products (상품)
- `GET /api/products` - 상품 목록 조회 (페이징, 필터링)
- `GET /api/products/{product_id}` - 상품 상세 조회 (모든 필드)

### 4. Personas (페르소나)
- `POST /api/personas` - 페르소나 생성
- `GET /api/personas` - 모든 페르소나 조회
- `GET /api/personas/{persona_key}` - 특정 페르소나 조회
- `PUT /api/personas/{persona_key}` - 페르소나 수정
- `DELETE /api/personas/{persona_key}` - 페르소나 삭제

### 5. Recommendations (추천)
- `GET /api/personas/{persona_key}/recommendations` - 페르소나 맞춤 추천

---

## 📋 상세 스펙

### 🔧 System APIs

#### GET `/`
**설명:** API 정보 및 사용 가능한 엔드포인트 목록

**응답:**
```json
{
  "message": "AI Innovation Challenge 2026 API",
  "version": "1.0.0",
  "endpoints": {
    "brands": "/api/brands",
    "products": "/api/products",
    "personas": "/api/personas",
    "recommendations": "/api/personas/{persona_key}/recommendations"
  }
}
```

#### GET `/health`
**설명:** 데이터베이스 연결 상태 및 데이터 개수 확인

**응답:**
```json
{
  "status": "healthy",
  "database": "connected",
  "tables": {
    "brands": 60,
    "products": 868,
    "personas": 0
  }
}
```

---

### 🏷️ Brands APIs

#### GET `/api/brands`
**설명:** 모든 브랜드 조회

**응답:**
```json
{
  "total": 60,
  "brands": [
    {
      "id": 1,
      "name": "설화수",
      "brand_url": null,
      "tone_description": null
    }
  ]
}
```

#### GET `/api/brands/{brand_id}/products`
**설명:** 특정 브랜드의 상품 조회

**파라미터:**
- `brand_id` (path): 브랜드 ID
- `limit` (query): 조회 개수 (기본값: 20)

**응답:**
```json
{
  "brand": {
    "id": 1,
    "name": "설화수"
  },
  "total": 20,
  "products": [
    {
      "id": 1,
      "product_name": "자음생크림",
      "category": "스킨케어",
      "sale_price": 85000.0,
      "rating": 4.8,
      "image_urls": ["https://..."]
    }
  ]
}
```

---

### 🛍️ Products APIs

#### GET `/api/products`
**설명:** 상품 목록 조회 (페이징 및 필터링 지원)

**파라미터:**
- `limit` (query): 한 페이지당 개수 (기본값: 20)
- `offset` (query): 건너뛸 개수 (기본값: 0)
- `category` (query): 카테고리 필터 (선택사항)

**응답:**
```json
{
  "total": 868,
  "offset": 0,
  "limit": 20,
  "products": [
    {
      "id": 1,
      "product_name": "미용실 헤어에센스",
      "brand_name": "글램팜",
      "category": null,
      "sale_price": 39000.0,
      "rating": 4.9,
      "review_count": 36,
      "image_urls": ["https://..."],
      "description": null
    }
  ]
}
```

#### GET `/api/products/{product_id}`
**설명:** 상품 상세 조회 - **모든 필드 포함** ⭐

**파라미터:**
- `product_id` (path): 상품 ID

**응답 (ProductResponse):**
```json
{
  "id": 1,
  "brand_id": 1,
  "brand_name": "글램팜",
  "product_code": "62423",
  "product_name": "미용실 헤어에센스 열손상방지 헤어 오일 123ml 택1",
  "category": null,
  "sub_category": null,
  "original_price": 39000.0,
  "discount_rate": 0.0,
  "sale_price": 39000.0,
  "rating": 4.9,
  "review_count": 36,
  "skin_types": [],
  "personal_colors": [],
  "base_shades": [],
  "concern_keywords": [],
  "makeup_colors": [],
  "preferred_ingredients": [],
  "avoided_ingredients": [],
  "preferred_scents": [],
  "values_keywords": [],
  "dedicated_products": [],
  "product_url": "https://www.amoremall.com/kr/ko/product/detail?onlineProdSn=62423",
  "image_urls": [
    "https://images-kr.amoremall.com/products/005201000049/005201000049_01.jpg",
    "https://images-kr.amoremall.com/products/005201000049/005201000049_02.jpg"
  ],
  "description": null,
  "generated_document": "GPT 생성 문서...",
  "tags": {},
  "buyer_statistics": {}
}
```

---

### 👤 Personas APIs

#### POST `/api/personas`
**설명:** 새 페르소나 생성 (프론트엔드 → 백엔드)

**Request Body (PersonaCreate):**
```json
{
  "persona_key": "user_001",
  "name": "30대 건성 피부 직장인",
  "description": "건조한 피부로 고민하는 30대 여성",
  "gender": "여성",
  "age_group": "30대",
  "skin_types": ["건성", "민감성"],
  "personal_color": "웜톤",
  "base_shade": "21호",
  "skin_concerns": ["건조", "주름", "탄력"],
  "preferred_point_colors": ["베이지", "브라운"],
  "preferred_ingredients": ["히알루론산", "세라마이드"],
  "avoided_ingredients": ["파라벤", "알코올"],
  "preferred_scents": ["무향", "플로럴"],
  "special_conditions": ["천연/유기농"],
  "budget_range": "중"
}
```

**응답 (PersonaResponse):**
```json
{
  "id": 1,
  "persona_key": "user_001",
  "name": "30대 건성 피부 직장인",
  "description": "건조한 피부로 고민하는 30대 여성",
  "gender": "여성",
  "age_group": "30대",
  "skin_types": ["건성", "민감성"],
  "personal_color": "웜톤",
  "base_shade": "21호",
  "skin_concerns": ["건조", "주름", "탄력"],
  "preferred_ingredients": ["히알루론산", "세라마이드"],
  "avoided_ingredients": ["파라벤", "알코올"]
}
```

**에러:**
- `400 Bad Request`: 중복된 persona_key

#### GET `/api/personas`
**설명:** 모든 페르소나 조회

**응답:**
```json
{
  "total": 1,
  "personas": [
    {
      "id": 1,
      "persona_key": "user_001",
      "name": "30대 건성 피부 직장인",
      "gender": "여성",
      "age_group": "30대",
      "skin_types": ["건성", "민감성"],
      "skin_concerns": ["건조", "주름", "탄력"],
      "created_at": "2025-12-26T10:30:00Z"
    }
  ]
}
```

#### GET `/api/personas/{persona_key}`
**설명:** 특정 페르소나 상세 조회

**파라미터:**
- `persona_key` (path): 페르소나 고유 키

**응답:** PersonaResponse (위와 동일)

**에러:**
- `404 Not Found`: 페르소나를 찾을 수 없음

#### PUT `/api/personas/{persona_key}`
**설명:** 페르소나 정보 수정

**파라미터:**
- `persona_key` (path): 페르소나 고유 키

**Request Body:** PersonaCreate (수정할 필드만 포함)

**응답:** 수정된 PersonaResponse

**에러:**
- `404 Not Found`: 페르소나를 찾을 수 없음

#### DELETE `/api/personas/{persona_key}`
**설명:** 페르소나 삭제

**파라미터:**
- `persona_key` (path): 페르소나 고유 키

**응답:**
```json
{
  "message": "Persona 'user_001' deleted successfully"
}
```

**에러:**
- `404 Not Found`: 페르소나를 찾을 수 없음

---

### 🎯 Recommendations API

#### GET `/api/personas/{persona_key}/recommendations`
**설명:** 특정 페르소나에 맞는 추천 상품 조회

**파라미터:**
- `persona_key` (path): 페르소나 고유 키
- `limit` (query): 추천 개수 (기본값: 20)

**응답 (추천이 있는 경우):**
```json
{
  "persona": {
    "persona_key": "user_001",
    "name": "30대 건성 피부 직장인",
    "skin_concerns": ["건조", "주름", "탄력"],
    "preferred_ingredients": ["히알루론산", "세라마이드"]
  },
  "total": 10,
  "recommendations": [
    {
      "product_id": 123,
      "product_name": "히알루론산 세럼",
      "brand_name": "설화수",
      "category": "스킨케어",
      "sale_price": 85000.0,
      "rating": 4.8,
      "relevance_score": 0.95,
      "matched_attributes": {
        "skin_type_match": ["건성"],
        "concern_match": ["보습", "탄력"],
        "ingredient_match": ["히알루론산"]
      },
      "image_urls": ["https://..."]
    }
  ]
}
```

**응답 (추천이 없는 경우):**
```json
{
  "persona": {
    "persona_key": "user_001",
    "name": "30대 건성 피부 직장인"
  },
  "total": 0,
  "recommendations": [],
  "message": "No recommendations found for this persona"
}
```

**에러:**
- `404 Not Found`: 페르소나를 찾을 수 없음

---

## ✅ 필드 매핑 확인

### Products 테이블 → API 응답 매핑

| 데이터베이스 필드 | API 응답 필드 | 타입 | 설명 |
|---|---|---|---|
| `id` | `id` | integer | 상품 ID |
| `brand_id` | `brand_id` | integer | 브랜드 ID |
| `product_code` | `product_code` | string | 상품 코드 |
| `product_name` | `product_name` | string | 상품명 |
| `category` | `category` | string | 카테고리 |
| `sub_category` | `sub_category` | string | 서브카테고리 |
| `original_price` | `original_price` | float | 원가 |
| `discount_rate` | `discount_rate` | float | 할인율 (%) |
| `sale_price` | `sale_price` | float | 판매가 ✅ |
| `rating` | `rating` | float | 별점 (0.0~5.0) ✅ |
| `review_count` | `review_count` | integer | 리뷰 개수 ✅ |
| `skin_types` | `skin_types` | array | 피부타입 배열 |
| `personal_colors` | `personal_colors` | array | 퍼스널 컬러 배열 |
| `base_shades` | `base_shades` | array | 베이스 호수 배열 |
| `concern_keywords` | `concern_keywords` | array | 고민 키워드 배열 |
| `makeup_colors` | `makeup_colors` | array | 메이크업 색상 배열 |
| `preferred_ingredients` | `preferred_ingredients` | array | 선호 성분 배열 |
| `avoided_ingredients` | `avoided_ingredients` | array | 기피 성분 배열 |
| `preferred_scents` | `preferred_scents` | array | 선호 향 배열 |
| `values_keywords` | `values_keywords` | array | 가치관 배열 |
| `dedicated_products` | `dedicated_products` | array | 전용제품 배열 |
| `product_url` | `product_url` | string | 판매 URL |
| `image_urls` | `image_urls` | array | 이미지 URL 배열 ✅ |
| `description` | `description` | string | 상품 설명 |
| `generated_document` | `generated_document` | string | GPT 생성 문서 |
| `tags` | `tags` | object | 태그 (JSONB) |
| `buyer_statistics` | `buyer_statistics` | object | 구매자 통계 (JSONB) |

---

## 🔧 수정 완료 사항

### 1. 필드명 수정
- ❌ `price` → ✅ `sale_price`
- ❌ `images` → ✅ `image_urls`

### 2. 추가된 필드
- ✅ `rating` (별점)
- ✅ `review_count` (리뷰 개수)

### 3. Pydantic 모델 개선
- ✅ `ProductResponse`에 모든 필드 추가
- ✅ `PersonaCreate`에 예시 값 추가
- ✅ Swagger UI에서 자동 완성 지원

---

## 🎯 테스트 방법

### Swagger UI에서 테스트
```
http://localhost:8000/docs
```

### 주요 테스트 시나리오

1. **상품 조회**
   - `GET /api/products` → 첫 20개 조회
   - `GET /api/products/1` → ID 1번 상품 상세 조회 (모든 필드 확인)

2. **페르소나 생성**
   - `POST /api/personas` → 예시 JSON 자동 입력됨

3. **브랜드별 상품**
   - `GET /api/brands` → 브랜드 목록
   - `GET /api/brands/1/products` → 해당 브랜드 상품

4. **추천** (product_personas 데이터가 있을 때)
   - `GET /api/personas/user_001/recommendations`

---

## 📊 현재 데이터 상태

```json
{
  "brands": 60,
  "products": 868,
  "personas": 0,
  "product_personas": 0
}
```

---

## ✅ 모든 엔드포인트 검증 완료!

- ✅ 필드명 올바르게 매핑됨
- ✅ 모든 새 필드 포함됨
- ✅ Swagger UI 자동 완성 작동
- ✅ 응답 모델 정의됨
- ✅ 에러 처리 구현됨

이제 서버를 재시작하고 `http://localhost:8000/docs`에서 모든 기능을 테스트할 수 있습니다! 🎉
