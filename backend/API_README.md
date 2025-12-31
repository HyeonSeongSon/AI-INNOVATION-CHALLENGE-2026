# CRM Agent API 사용 가이드

## 📋 개요

웹 환경에서 AI 기반 CRM 메시지 생성을 위한 FastAPI 서버입니다.
사용자 인터럽트 기반으로 상품 추천 및 메시지 생성을 처리합니다.

## 🚀 실행 방법

### 1. 서버 시작

```bash
cd backend
python main.py
```

또는

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. API 문서 확인

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 3. 테스트 클라이언트 실행

브라우저에서 `test_client.html` 파일을 열면 바로 테스트 가능합니다.

## 📡 API 엔드포인트

### 1. POST `/api/crm/start` - 상품 추천 시작

사용자 메시지를 분석하여 상품을 추천합니다.

**요청:**
```json
{
  "user_message": "PERSONA_002로 신상품 홍보용 립스틱 광고 만들어줘"
}
```

**응답:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "products": [
    {
      "상품명": "노웨어 립스틱 바밍글로우",
      "브랜드": "에스쁘아",
      "판매가": 20400,
      "할인율": 15,
      "별점": 4.8,
      "리뷰_갯수": 1428,
      "vector_search_score": 0.8234
    },
    {
      "상품명": "루즈 클래시",
      "브랜드": "헤라",
      "판매가": 45000,
      "할인율": 10,
      "별점": 4.7,
      "리뷰_갯수": 1450
    },
    {
      "상품명": "센슈얼 틴티드 샤인스틱",
      "브랜드": "헤라",
      "판매가": 40500,
      "할인율": 10,
      "별점": 4.7,
      "리뷰_갯수": 1641
    }
  ]
}
```

### 2. POST `/api/crm/select` - 상품 선택 및 메시지 생성

선택한 상품으로 CRM 메시지를 생성합니다.

**요청:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "selected_index": 0
}
```

**응답:**
```json
{
  "title": "건조한 입술, 이제 촉촉하게",
  "message": "입술이 자주 갈라지시나요? 에스쁘아 노웨어 립스틱 바밍글로우로 하루 종일 촉촉한 입술을 경험해보세요. 비건 포뮬러로 건강하게, 생생한 컬러로 아름답게. 지금 15% 할인된 가격으로 만나보세요.",
  "selected_product": {
    "상품명": "노웨어 립스틱 바밍글로우",
    "브랜드": "에스쁘아",
    "판매가": 20400
  }
}
```

### 3. GET `/api/crm/session/{session_id}` - 세션 정보 조회

**응답:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "has_thread_id": true,
  "product_count": 3,
  "has_parsed_request": true
}
```

### 4. DELETE `/api/crm/session/{session_id}` - 세션 삭제

**응답:**
```json
{
  "message": "세션이 삭제되었습니다"
}
```

### 5. GET `/api/crm/sessions/count` - 활성 세션 개수

**응답:**
```json
{
  "active_sessions": 5,
  "session_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440111"
  ]
}
```

## 🔄 워크플로우

```
1. 프론트엔드: POST /api/crm/start
   ↓
   사용자 메시지 분석 → 상품 추천
   ↓
2. 프론트엔드: 추천 상품 3개 표시
   ↓
3. 사용자: 상품 선택 (0, 1, 2 중 하나)
   ↓
4. 프론트엔드: POST /api/crm/select
   ↓
   선택된 상품으로 메시지 생성
   ↓
5. 프론트엔드: 생성된 메시지 표시
```

## 📝 프론트엔드 예제 코드

### JavaScript (Fetch API)

```javascript
// 1단계: 상품 추천
async function startRecommendation() {
  const response = await fetch('http://localhost:8000/api/crm/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_message: "PERSONA_002로 신상품 홍보용 립스틱 광고 만들어줘"
    })
  });

  const data = await response.json();
  const sessionId = data.session_id;
  const products = data.products;

  // 상품 목록 표시
  displayProducts(products);

  return sessionId;
}

// 2단계: 메시지 생성
async function generateMessage(sessionId, selectedIndex) {
  const response = await fetch('http://localhost:8000/api/crm/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      selected_index: selectedIndex
    })
  });

  const data = await response.json();
  const title = data.title;
  const message = data.message;

  // 메시지 표시
  displayMessage(title, message);
}
```

### Python (Requests)

```python
import requests

# 1단계: 상품 추천
response = requests.post(
    'http://localhost:8000/api/crm/start',
    json={
        'user_message': 'PERSONA_002로 신상품 홍보용 립스틱 광고 만들어줘'
    }
)

data = response.json()
session_id = data['session_id']
products = data['products']

print(f"추천 상품 {len(products)}개:")
for i, product in enumerate(products):
    print(f"{i}. {product['상품명']} ({product['브랜드']})")

# 사용자 선택
selected_index = int(input("상품 번호 선택: "))

# 2단계: 메시지 생성
response = requests.post(
    'http://localhost:8000/api/crm/select',
    json={
        'session_id': session_id,
        'selected_index': selected_index
    }
)

data = response.json()
print(f"\n제목: {data['title']}")
print(f"메시지: {data['message']}")
```

## ⚠️ 주의사항

1. **세션 관리**
   - 세션은 메모리에 저장됩니다 (개발 환경용)
   - 프로덕션에서는 Redis 등 사용 권장
   - 서버 재시작 시 모든 세션 삭제됨

2. **타임아웃**
   - 세션은 자동으로 삭제되지 않습니다
   - 필요 시 DELETE 엔드포인트로 수동 삭제

3. **에러 처리**
   - 모든 에러는 HTTPException으로 반환
   - status_code와 detail 확인 필수

## 🛠️ 프로덕션 배포

### Redis 사용 (권장)

```python
import redis
from typing import Dict, Any

# Redis 연결
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# 세션 저장
def save_session(session_id: str, data: Dict[str, Any]):
    redis_client.setex(
        f"session:{session_id}",
        3600,  # 1시간 TTL
        json.dumps(data)
    )

# 세션 조회
def get_session(session_id: str) -> Dict[str, Any]:
    data = redis_client.get(f"session:{session_id}")
    return json.loads(data) if data else None
```

### Docker 배포

```dockerfile
FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 📊 모니터링

```bash
# 활성 세션 확인
curl http://localhost:8000/api/crm/sessions/count

# 특정 세션 정보
curl http://localhost:8000/api/crm/session/{session_id}
```

## 🐛 트러블슈팅

### 1. CORS 에러
```
Access to fetch at 'http://localhost:8000/api/crm/start' from origin 'http://localhost:3000' has been blocked by CORS policy
```

**해결:** `main.py`에서 CORS 설정 확인
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 프론트엔드 URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. 세션 만료
```
404: 세션을 찾을 수 없습니다
```

**해결:**
- 1단계부터 다시 시작
- 세션 ID 확인
- 서버 재시작 여부 확인

### 3. LLM API 에러
```
500: 상품 추천 중 오류 발생
```

**해결:**
- `.env` 파일에 OPENAI_API_KEY 확인
- API 잔액 확인
- 로그 확인

## 📞 문의

문제가 발생하면 GitHub Issues에 등록해주세요.
