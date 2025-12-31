# OpenSearch 하이브리드 검색 시스템

## 📋 프로젝트 개요

OpenSearch를 활용한 **하이브리드 검색 시스템**으로, BM25 키워드 검색과 KNN 벡터 검색을 결합하여 상품 추천 기능을 제공합니다.

### 주요 기능
- 🔍 **하이브리드 검색**: BM25(키워드) + KNN(벡터 유사도) 결합
- 🎯 **Product ID 필터링**: 특정 상품 ID 리스트 내에서 검색
- 🤖 **의미 기반 검색**: 한국어 임베딩 모델(KURE-v1) 사용
- ⚖️ **가중치 조절 가능**: 키워드 40% + 벡터 60% (조정 가능)
- 🚀 **FastAPI 기반**: REST API 제공

---

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐
│   FastAPI       │  포트 8010
│   (검색 API)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  OpenSearch     │  포트 9200
│  3-Node Cluster │
│  - node1 (9200) │
│  - node2 (9201) │
│  - node3 (9202) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Vector Database │
│ - BM25 Index    │
│ - KNN Index     │
│ - 1024 차원 벡터 │
└─────────────────┘
```

---

## 🚀 빠른 시작

### 1. 필수 요구사항

- Docker & Docker Compose
- Python 3.11+
- 최소 4GB RAM (OpenSearch 클러스터용)

### 2. 저장소 클론

```bash
git clone <repository-url>
cd skn_final_opensearch
```

### 3. Python 패키지 설치

```bash
# 가상환경 생성 (선택사항)
python -m venv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 필수 패키지 설치
pip install -r requirements.txt
```

### 4. 환경 변수 설정

**.env.example 파일을 참고하여 .env 파일 생성:**

```bash
# .env.example을 복사하여 .env 파일 생성
cp .env.example .env

# 필요시 .env 파일 편집
nano .env
```

**로컬 개발 환경 (.env.example 참고):**
```bash
OPENSEARCH_ADMIN_PASSWORD=MyStrongPassword123!
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8010

ENVIRONMENT=local
```

**AWS 프로덕션 환경:**
- `.env.production.example`을 참고하여 `.env.production` 파일 생성
- 자세한 내용은 [DEPLOYMENT.md](DEPLOYMENT.md) 참조

### 5. Docker Compose로 전체 시스템 실행

```bash
# 전체 시스템 시작 (OpenSearch + FastAPI)
docker compose up -d

# 로그 확인
docker compose logs -f

# 상태 확인
docker compose ps
```

### 6. 접속 확인

- **OpenSearch**: http://localhost:9200
- **OpenSearch Dashboards**: http://localhost:5601
- **FastAPI 문서**: http://localhost:8010/docs
- **Health Check**: http://localhost:8010/health

---

## 📊 데이터 색인 (Indexing)

### 1. 데이터 준비

데이터 파일: `2512252207_with_product_id.jsonl`

**데이터 구조:**
```json
{
  "product_id": "20251200001",
  "태그": "립스틱",
  "브랜드": "에스쁘아",
  "상품명": "촉촉한 립스틱",
  "문서": "상품 상세 설명...",
  "퍼스널컬러": ["웜톤", "쿨톤"],
  "피부호수": "21호",
  "페르소나태그": {
    "피부타입": ["건성"],
    "고민키워드": ["보습"]
  }
}
```

### 2. 인덱스 생성 및 데이터 색인

```bash
# 방법 1: Python 스크립트 실행
python index_products.py

# 방법 2: 로컬에서 실행 (가상환경 사용)
pip install -r requirements.txt
python index_products.py
```

**색인 과정:**
1. OpenSearch 연결
2. 인덱스 매핑 생성 (1024차원 벡터 필드 포함)
3. 한국어 임베딩 모델(KURE-v1)로 벡터 생성
4. Bulk API로 데이터 색인
5. Search Pipeline 생성

### 3. 색인 확인

```bash
# 인덱스 확인
curl -X GET "localhost:9200/_cat/indices?v"

# 문서 개수 확인
curl -X GET "localhost:9200/product_index/_count?pretty"

# 샘플 데이터 조회
curl -X GET "localhost:9200/product_index/_search?size=1&pretty"
```

---

## 🔧 API 사용법

### 엔드포인트 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | API 정보 |
| GET | `/health` | 헬스체크 |
| GET | `/docs` | Swagger UI |
| POST | `/api/search/product-ids` | Product ID 필터링 검색 |

---

### 1. Product ID 필터링 검색

특정 상품 ID 리스트 내에서 쿼리에 맞는 상품을 검색합니다.

**엔드포인트:** `POST /api/search/product-ids`

**요청 예시:**
```bash
curl -X POST "http://localhost:8010/api/search/product-ids" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "촉촉한 립스틱",
    "product_ids": [
      "20251200462",
      "20251200463",
      "20251200464"
    ],
    "top_k": 3
  }'
```

**Python 예시:**
```python
import requests

url = "http://localhost:8010/api/search/product-ids"
data = {
    "query": "촉촉한 립스틱",
    "product_ids": [
        "20251200462",
        "20251200463",
        "20251200464"
    ],
    "top_k": 3
}

response = requests.post(url, json=data)
print(response.json())
```

**응답 예시:**
```json
{
  "success": true,
  "total_results": 3,
  "query": "촉촉한 립스틱",
  "product_id_filter": ["20251200462", "20251200463", "20251200464"],
  "results": [
    {
      "score": 1.9604945,
      "product_id": "20251200462",
      "브랜드": "에스쁘아",
      "상품명": "[NEW COLOR] 노웨어 립스틱 바밍글로우 3g",
      "태그": "립스틱",
      "문서": "1) 핵심 훅킹 - 메인 카피 & 캐치프레이즈..."
    }
  ]
}
```

**요청 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| query | string | ✅ | - | 검색 쿼리 텍스트 |
| product_ids | array[string] | ✅ | - | 검색할 상품 ID 리스트 |
| index_name | string | ❌ | product_index | 인덱스 이름 |
| pipeline_id | string | ❌ | hybrid-minmax-pipeline | 파이프라인 ID |
| top_k | integer | ❌ | 3 | 반환할 결과 개수 (1-100) |

---

## ⚙️ 설정 및 환경 변수

### 환경 변수 (.env)

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

### 하이브리드 검색 가중치 조정

**파일:** `opensearch_hybrid.py`

```python
# 220-225번 라인
"combination": {
    "technique": "arithmetic_mean",
    "parameters": {
        "weights": [0.4, 0.6]  # [BM25, KNN]
    }
}
```

- `[0.4, 0.6]`: 키워드 40%, 벡터 60% (기본값, 추천)
- `[0.3, 0.7]`: 의미 검색 강화
- `[0.5, 0.5]`: 균형잡힌 검색
- `[0.7, 0.3]`: 키워드 검색 강화

---

## 📁 프로젝트 구조

```
skn_final_opensearch/
├── opensearch_api.py              # FastAPI 서버
├── opensearch_hybrid.py           # OpenSearch 클라이언트
├── index_products.py              # 데이터 색인 스크립트
├── hybrid_search_example.py       # 검색 예제
├── brand_filter_search.py         # 브랜드 필터 검색
├── docker-compose.yml             # Docker Compose 설정
├── .env                           # 로컬 환경 변수
├── .env.production.example        # AWS 배포용 예시
├── requirements.txt               # Python 패키지
├── 2512252207_with_product_id.jsonl  # 상품 데이터
├── DEPLOYMENT.md                  # 배포 가이드
└── README.md                      # 이 파일
```

---

## 🐳 Docker 명령어

### 기본 명령어

```bash
# 전체 시작
docker compose up -d

# 전체 중지
docker compose down

# 특정 서비스만 재시작
docker compose restart fastapi-search

# 로그 확인
docker compose logs -f fastapi-search
docker compose logs -f opensearch-node1

# 컨테이너 상태 확인
docker compose ps

# 볼륨 포함 전체 삭제 (주의!)
docker compose down -v
```

### OpenSearch 클러스터 관리

```bash
# 클러스터 상태 확인
curl -X GET "localhost:9200/_cluster/health?pretty"

# 노드 확인
curl -X GET "localhost:9200/_cat/nodes?v"

# 인덱스 확인
curl -X GET "localhost:9200/_cat/indices?v"

# 인덱스 삭제 (재색인 시)
curl -X DELETE "localhost:9200/product_index"
```

---

## 🔍 검색 원리

### 하이브리드 검색 동작 방식

1. **사용자 쿼리 입력**: "촉촉한 립스틱"

2. **BM25 검색 (키워드)**
   - 텍스트 필드에서 키워드 매칭
   - 필드별 가중치 적용:
     - 문서: 3.0
     - 상품명: 2.0
     - 브랜드: 2.0
     - 태그: 1.5
     - 피부타입: 1.2
     - 고민키워드: 1.2
     - 전용제품: 1.0
     - 퍼스널컬러: 1.0
     - 피부호수: 1.0

3. **KNN 검색 (벡터 유사도)**
   - 쿼리를 1024차원 벡터로 임베딩 (KURE-v1 모델)
   - 코사인 유사도로 가장 가까운 벡터 검색

4. **점수 정규화 및 결합**
   - Min-Max 정규화
   - 가중 평균: BM25(40%) + KNN(60%)

5. **결과 반환**
   - 최종 점수 순으로 정렬
   - top_k개 반환

---

## 🧪 테스트

### 1. 간단한 검색 테스트

```bash
# Swagger UI에서 테스트
open http://localhost:8010/docs
```

### 2. Python 스크립트로 테스트

```python
# hybrid_search_example.py 실행
python hybrid_search_example.py

# 옵션 선택
# 1. 테스트 쿼리 실행
# 2. 직접 입력
```

### 3. cURL로 테스트

```bash
curl -X POST "http://localhost:8010/api/search/product-ids" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "보습 크림",
    "product_ids": ["20251200001", "20251200002"],
    "top_k": 5
  }'
```

---

## 📈 성능 최적화

### 1. 인덱스 설정

- **Refresh Interval**: 색인 중에는 `-1`로 설정, 완료 후 `1s`로 복원
- **Replica 설정**: 프로덕션에서는 최소 1개 replica 권장

### 2. 검색 최적화

- **top_k 조정**: 필요한 만큼만 요청 (기본값: 3)
- **Product ID 필터링**: 검색 범위를 좁혀 성능 향상
- **캐싱**: 자주 사용되는 쿼리는 애플리케이션 레벨에서 캐싱

### 3. 리소스 관리

```yaml
# docker-compose.yml에서 메모리 설정
OPENSEARCH_JAVA_OPTS: -Xms512m -Xmx512m  # 힙 메모리
resources:
  limits:
    memory: 1g  # 컨테이너 전체 메모리
```

---

## 🚨 트러블슈팅

### 문제 1: OpenSearch 연결 실패

```bash
# OpenSearch가 실행 중인지 확인
docker compose ps opensearch-node1

# 로그 확인
docker compose logs opensearch-node1

# 헬스체크
curl http://localhost:9200/_cluster/health
```

### 문제 2: 색인 실패

```bash
# 인덱스 상태 확인
curl -X GET "localhost:9200/product_index/_stats?pretty"

# 매핑 확인
curl -X GET "localhost:9200/product_index/_mapping?pretty"

# 인덱스 삭제 후 재색인
curl -X DELETE "localhost:9200/product_index"
python index_products.py
```

### 문제 3: 검색 결과 없음

- Product ID가 실제 인덱스에 있는지 확인
- `product_id.keyword` vs `product_id` 필드 확인
- 로그 확인: `docker compose logs fastapi-search`

### 문제 4: 메모리 부족

```bash
# Docker 메모리 할당 증가
# Docker Desktop > Settings > Resources > Memory: 6GB 이상 권장
```

---

## 🌐 AWS 배포

상세한 AWS 배포 가이드는 [DEPLOYMENT.md](DEPLOYMENT.md)를 참조하세요.

**간단 요약:**

```bash
# 1. .env.production 생성
cp .env.production.example .env.production

# 2. AWS OpenSearch 정보 입력
nano .env.production

# 3. EC2에서 실행
python opensearch_api.py
```

---

## 📝 라이선스

MIT License

---

## 👥 기여

이슈 및 풀 리퀘스트는 언제든 환영합니다!

---

## 📞 문의

프로젝트 관련 문의사항은 이슈를 등록해주세요.
