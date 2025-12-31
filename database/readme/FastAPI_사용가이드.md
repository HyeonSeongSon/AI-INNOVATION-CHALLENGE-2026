# FastAPI 서버 사용 가이드

## ✅ 현재 상태

**API 서버:** 🟢 실행 중
**주소:** `http://localhost:8000`
**데이터베이스:** ✅ 연결됨
- **브랜드:** 60개
- **상품:** 868개
- **페르소나:** 0개

---

## 🌐 접속 주소

### 1. Swagger UI (대화형 API 문서)
```
http://localhost:8000/docs
```
- 브라우저에서 **바로 API 테스트** 가능
- 모든 엔드포인트 목록 및 설명
- "Try it out" 버튼으로 즉시 실행

### 2. ReDoc (읽기 전용 문서)
```
http://localhost:8000/redoc
```
- 깔끔한 문서 형식
- API 구조 한눈에 보기

### 3. OpenAPI JSON
```
http://localhost:8000/openapi.json
```
- API 스키마 JSON 파일

---

## 📡 주요 API 엔드포인트

### 🏥 Health Check

**GET** `/health`

데이터베이스 연결 상태 및 데이터 개수 확인

```bash
curl http://localhost:8000/health
```

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

### 🏷️ 브랜드 API

#### 1. 모든 브랜드 조회
**GET** `/api/brands`

```bash
curl http://localhost:8000/api/brands
```

**응답:**
```json
[
  {
    "id": 1,
    "name": "설화수",
    "brand_url": null,
    "tone_description": null
  },
  {
    "id": 2,
    "name": "글램팜",
    "brand_url": null,
    "tone_description": null
  }
]
```

#### 2. 특정 브랜드의 상품 조회
**GET** `/api/brands/{brand_id}/products`

```bash
curl http://localhost:8000/api/brands/1/products
```

---

### 🛍️ 상품 API

#### 1. 상품 목록 조회 (페이징)
**GET** `/api/products`

**쿼리 파라미터:**
- `limit`: 한 번에 가져올 개수 (기본값: 20)
- `offset`: 건너뛸 개수 (기본값: 0)
- `category`: 카테고리 필터 (선택사항)

```bash
# 처음 20개
curl http://localhost:8000/api/products

# 다음 20개
curl http://localhost:8000/api/products?offset=20&limit=20

# 카테고리 필터링
curl "http://localhost:8000/api/products?category=스킨케어"
```

**응답:**
```json
{
  "total": 868,
  "limit": 20,
  "offset": 0,
  "products": [
    {
      "id": 1,
      "brand_name": "글램팜",
      "product_name": "미용실 헤어에센스...",
      "category": null,
      "price": 39000.0,
      "images": ["https://..."],
      "description": null,
      "generated_document": "..."
    }
  ]
}
```

#### 2. 특정 상품 상세 조회
**GET** `/api/products/{product_id}`

```bash
curl http://localhost:8000/api/products/1
```

**응답:**
```json
{
  "id": 1,
  "brand_id": 1,
  "brand_name": "글램팜",
  "product_name": "미용실 헤어에센스...",
  "original_price": 39000.0,
  "discount_rate": 0.0,
  "sale_price": 39000.0,
  "rating": 4.9,
  "review_count": 36,
  "skin_types": ["건성", "지성"],
  "concern_keywords": ["보습", "진정"],
  "preferred_ingredients": ["히알루론산"],
  "avoided_ingredients": ["파라벤"],
  "image_urls": ["https://..."],
  "product_url": "https://...",
  "generated_document": "...",
  "tags": {},
  "buyer_statistics": {}
}
```

---

### 👤 페르소나 API

#### 1. 페르소나 생성
**POST** `/api/personas`

**요청 본문:**
```json
{
  "persona_key": "user_001",
  "name": "30대 건성 피부 직장인",
  "description": "건성 피부 고민이 있는 30대 여성",
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

**curl 예시:**
```bash
curl -X POST http://localhost:8000/api/personas \
  -H "Content-Type: application/json" \
  -d '{
    "persona_key": "user_001",
    "name": "30대 건성 피부 직장인",
    "gender": "여성",
    "age_group": "30대",
    "skin_types": ["건성", "민감성"],
    "skin_concerns": ["건조", "주름", "탄력"]
  }'
```

#### 2. 모든 페르소나 조회
**GET** `/api/personas`

```bash
curl http://localhost:8000/api/personas
```

#### 3. 특정 페르소나 조회
**GET** `/api/personas/{persona_key}`

```bash
curl http://localhost:8000/api/personas/user_001
```

#### 4. 페르소나 수정
**PUT** `/api/personas/{persona_key}`

```bash
curl -X PUT http://localhost:8000/api/personas/user_001 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "30대 건성 피부 직장인 (수정됨)",
    "skin_concerns": ["건조", "탄력", "주름개선"]
  }'
```

#### 5. 페르소나 삭제
**DELETE** `/api/personas/{persona_key}`

```bash
curl -X DELETE http://localhost:8000/api/personas/user_001
```

---

### 🎯 추천 API

#### 페르소나 맞춤 상품 추천
**GET** `/api/personas/{persona_key}/recommendations`

**쿼리 파라미터:**
- `limit`: 추천 개수 (기본값: 20)

```bash
curl http://localhost:8000/api/personas/user_001/recommendations?limit=10
```

**응답:**
```json
{
  "persona": {
    "persona_key": "user_001",
    "name": "30대 건성 피부 직장인"
  },
  "total": 10,
  "recommendations": [
    {
      "product_id": 123,
      "product_name": "히알루론산 세럼",
      "brand_name": "설화수",
      "category": "스킨케어",
      "sale_price": 45000.0,
      "rating": 4.8,
      "relevance_score": 0.95,
      "matched_attributes": {
        "skin_type_match": ["건성"],
        "concern_match": ["보습", "탄력"],
        "ingredient_match": ["히알루론산"]
      }
    }
  ]
}
```

---

## 🖥️ 브라우저에서 사용하기 (Swagger UI)

### STEP 1: Swagger UI 접속

브라우저에서 다음 주소를 열어주세요:
```
http://localhost:8000/docs
```

### STEP 2: API 테스트

1. **엔드포인트 선택**
   - 왼쪽에서 원하는 API 클릭 (예: `GET /api/brands`)

2. **"Try it out" 버튼 클릭**

3. **파라미터 입력** (필요한 경우)
   - Path Parameters
   - Query Parameters
   - Request Body

4. **"Execute" 버튼 클릭**

5. **결과 확인**
   - Response body: JSON 응답
   - Response headers
   - Response code

### STEP 3: 페르소나 생성 예시 (Swagger UI)

1. `POST /api/personas` 클릭
2. "Try it out" 클릭
3. Request body에 다음 JSON 입력:
   ```json
   {
     "persona_key": "test_user",
     "name": "테스트 사용자",
     "gender": "여성",
     "age_group": "20대",
     "skin_types": ["지성"],
     "skin_concerns": ["모공", "피지"]
   }
   ```
4. "Execute" 클릭
5. Response 확인

---

## 💻 PowerShell에서 사용하기

### 1. 브랜드 목록 조회
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/brands" -Method Get | ConvertTo-Json -Depth 10
```

### 2. 상품 검색
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/products?limit=5" -Method Get | ConvertTo-Json -Depth 10
```

### 3. 페르소나 생성
```powershell
$personaData = @{
    persona_key = "user_001"
    name = "30대 여성"
    gender = "여성"
    age_group = "30대"
    skin_types = @("건성")
    skin_concerns = @("건조", "주름")
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/personas" -Method Post -Body $personaData -ContentType "application/json"
```

---

## 📊 데이터 탐색 예시

### 1. 가격대별 상품 검색

```bash
# 3만원 이하 상품
curl "http://localhost:8000/api/products?limit=100" | jq '.products[] | select(.sale_price <= 30000)'

# 고가 상품
curl "http://localhost:8000/api/products?limit=100" | jq '.products[] | select(.sale_price >= 100000)'
```

### 2. 별점 높은 상품

```bash
# 별점 4.5 이상, 리뷰 20개 이상
curl "http://localhost:8000/api/products?limit=100" | jq '.products[] | select(.rating >= 4.5 and .review_count >= 20)'
```

### 3. 특정 성분 포함 상품

```bash
# 히알루론산 포함
curl "http://localhost:8000/api/products?limit=100" | jq '.products[] | select(.preferred_ingredients[]? == "히알루론산")'
```

---

## 🔧 서버 관리

### 서버 상태 확인
```bash
curl http://localhost:8000/health
```

### 서버 중지
PowerShell에서:
```powershell
# 프로세스 ID 확인
netstat -ano | findstr :8000

# 프로세스 종료 (PID를 실제 번호로 변경)
taskkill /PID <프로세스ID> /F
```

### 서버 재시작
```bash
cd AI-INNOVATION-CHALLENGE-2026-hs_branch/database
python api_server.py
```

---

## 🎨 프론트엔드 통합 예시

### JavaScript (Fetch API)

```javascript
// 1. 브랜드 목록 가져오기
fetch('http://localhost:8000/api/brands')
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));

// 2. 페르소나 생성
const personaData = {
  persona_key: 'user_001',
  name: '30대 건성 피부',
  gender: '여성',
  age_group: '30대',
  skin_types: ['건성'],
  skin_concerns: ['건조', '주름']
};

fetch('http://localhost:8000/api/personas', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(personaData)
})
  .then(response => response.json())
  .then(data => console.log('Persona created:', data))
  .catch(error => console.error('Error:', error));

// 3. 추천 상품 가져오기
fetch('http://localhost:8000/api/personas/user_001/recommendations?limit=10')
  .then(response => response.json())
  .then(data => {
    console.log('Recommendations:', data.recommendations);
  })
  .catch(error => console.error('Error:', error));
```

### React 예시

```jsx
import React, { useState, useEffect } from 'react';

function ProductList() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/products?limit=20')
      .then(res => res.json())
      .then(data => {
        setProducts(data.products);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching products:', err);
        setLoading(false);
      });
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>상품 목록</h1>
      {products.map(product => (
        <div key={product.id}>
          <h2>{product.product_name}</h2>
          <p>브랜드: {product.brand_name}</p>
          <p>가격: {product.sale_price?.toLocaleString()}원</p>
          <p>평점: {product.rating} ({product.review_count}개 리뷰)</p>
        </div>
      ))}
    </div>
  );
}
```

---

## 📝 참고 사항

### CORS 설정
API 서버는 모든 도메인에서 접근 가능하도록 CORS가 설정되어 있습니다.

```python
# api_server.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

프로덕션 환경에서는 특정 도메인만 허용하도록 변경하세요.

### API 버전
현재 API 버전: **1.0.0**

---

## 🎉 완료!

이제 브라우저에서 `http://localhost:8000/docs`를 열어서 모든 API를 테스트할 수 있습니다!

**주요 기능:**
- ✅ 868개 상품 조회
- ✅ 60개 브랜드 조회
- ✅ 페르소나 생성/수정/삭제
- ✅ 페르소나 기반 상품 추천
- ✅ 가격, 평점, 카테고리 필터링
- ✅ 페이징 지원
