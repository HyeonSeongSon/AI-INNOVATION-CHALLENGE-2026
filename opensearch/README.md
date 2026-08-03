# OpenSearch 하이브리드 검색 시스템

## 프로젝트 개요

OpenSearch를 활용한 **하이브리드 검색 시스템**으로, BM25 키워드 검색과 KNN 벡터 검색을 결합하여 상품 추천 기능을 제공합니다.

### 주요 기능

- **하이브리드 검색**: BM25(키워드) + KNN(벡터 유사도) 결합
- **Product ID 필터링**: 특정 상품 ID 리스트 내에서 검색
- **의미 기반 검색**: 한국어 임베딩 모델(KURE-v1) 사용
- **가중치 조절 가능**: 키워드 40% + 벡터 60% (조정 가능)
- **FastAPI 기반**: REST API 제공

---

## 시스템 아키텍처

```
┌─────────────────┐
│   FastAPI       │  포트 8010
│   (검색 API)     │
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│  OpenSearch          │  포트 9200 (컨테이너 내부 전용)
│  3-Node Cluster      │
│  - opensearch-node1  │
│  - opensearch-node2  │
│  - opensearch-node3  │
└────────┬─────────────┘
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

## 빠른 시작

### 1. 필수 요구사항

- Docker & Docker Compose
- Python 3.11+
- 최소 4GB RAM (OpenSearch 클러스터용)

### 2. 저장소 클론

```bash
git clone https://github.com/HyeonSeongSon/AI-INNOVATION-CHALLENGE-2026.git
cd AI-INNOVATION-CHALLENGE-2026/opensearch
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
OPENSEARCH_ADMIN_PASSWORD=CHANGE_ME_STRONG_RANDOM
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200

FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8010

ENVIRONMENT=local
```

**AWS 프로덕션 환경:**

- 값은 Terraform/Secrets Manager가 주입하며, EC2 배포는 CI가 수행합니다
- 자세한 내용은 [../infra/DEPLOYMENT_GUIDE.md](../infra/DEPLOYMENT_GUIDE.md) 참조
- AWS 단일노드는 평문 HTTP(`plugins.security.disabled`)이므로 `OPENSEARCH_USE_SSL=false`,
  로컬 3노드 클러스터는 보안 활성(HTTPS)이라 compose가 `true`로 덮어씁니다

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

- **OpenSearch Dashboards**: http://localhost:5601

OpenSearch 엔진(9200)과 검색 API(8010)는 `msa-net` 내부에서만 접근할 수 있습니다
(compose에서 `expose`만 하고 호스트로 매핑하지 않음). 호스트에서 확인하려면 컨테이너를 경유합니다.

```bash
docker compose exec fastapi-search curl -sf http://localhost:8010/health
docker compose exec fastapi-search curl -sk https://opensearch-node1:9200/_cluster/health?pretty \
  -u admin:$OPENSEARCH_ADMIN_PASSWORD
```

---

## 데이터 파이프라인 실행

**전제**: OpenSearch 클러스터가 이미 떠 있어야 합니다(위 5단계). 아래는 순서대로 실행합니다.

```bash
# 1단계: 인덱스 매핑 + 검색 파이프라인 셋업
python setup_opensearch.py

# 2단계: v3 카테고리 색인 — skincare가 인덱스를 생성하므로 반드시 선행
python run_indexing_pipeline.py

# 3단계: v4 멀티벡터(문장단위) 색인 — 앱이 실제 검색에 쓰는 1차 인덱스
python index_products_v4_multivector.py

# 4단계: 품질검사용 금칙 문장 색인
python index_forbidden_sentences.py
```

**각 단계가 하는 일:**

| 단계 | 스크립트 | 내용 |
|---|---|---|
| 1 | `setup_opensearch.py` | 인덱스 매핑 생성(1024차원 벡터 필드 포함) + Search Pipeline 생성 |
| 2 | `run_indexing_pipeline.py` | 카테고리 7종을 순서대로 색인 — `skincare` → `color_tone` → `hair` → `living_supplies` → `fragrance_body` → `inner_beauty` → `beauty_tool`. 한국어 임베딩 모델(KURE-v1)로 벡터 생성 후 Bulk API 색인 |
| 3 | `index_products_v4_multivector.py` | 문장 단위 멀티벡터 색인 → `product_v4_*` 인덱스 |
| 4 | `index_forbidden_sentences.py` | `forbidden_sentences` 인덱스 색인 (메시지 품질검사 stage2에서 사용) |

> **2단계는 `skincare`가 인덱스를 생성**하므로 다른 카테고리보다 먼저 실행되어야 합니다.
> `run_indexing_pipeline.py`가 이 순서를 강제하므로 개별 실행보다 이 스크립트를 쓰는 편이 안전합니다.

> **주의: 이미 운영 중인 클러스터에 재색인하지 마세요.** 라이브 등록분이 덮여 소실될 수 있습니다.
> 재해 복구 시에는 재색인이 아니라 S3 스냅샷 복원(`restore_or_skip.sh`)을 사용합니다.

> 호스트에서 9200에 접근할 수 없으므로, 로컬 compose 환경에서는 컨테이너 안에서 실행합니다.
> 예: `docker compose exec fastapi-search python setup_opensearch.py`

---

### 색인 확인

```bash
# 인덱스 확인
curl -X GET "localhost:9200/_cat/indices?v"

# 문서 개수 확인
curl -X GET "localhost:9200/product_index_v3/_count?pretty"

# 샘플 데이터 조회
curl -X GET "localhost:9200/product_index_v3/_search?size=1&pretty"
```

> 위 명령은 9200에 직접 닿을 수 있는 환경(컨테이너 내부 또는 AWS EC2) 기준입니다.

---

## API 사용법

### 엔드포인트 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | API 정보 |
| GET | `/health` | 헬스체크 |
| GET | `/docs` | Swagger UI |
| GET | `/api/product/{product_id}` | 상품 단건 조회 |
| POST | `/api/search/product-ids` | Product ID 필터링 검색 |
| POST | `/api/search/combined` | 3차원(need/preference/persona) 병렬 검색 |
| POST | `/api/search/multivector` | v4 멀티벡터 검색 |
| POST | `/api/search/by-field` | 특정 필드 기준 검색 |
| POST | `/api/search/similar-sentences` | 유사 문장 검색 (품질검사 stage2) |
| POST | `/api/search/similar-sentences/batch` | 유사 문장 검색 배치 |
| POST | `/api/search/encode/batch` | 임베딩 배치 인코딩 |
| POST | `/api/product/index-multivector` | 런타임 단건 멀티벡터 색인 |

> 내부 서비스 전용 엔드포인트는 `INTERNAL_TOKEN` 검증을 거칩니다.

---

### Product ID 필터링 검색

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
| query | string | 필수 | - | 검색 쿼리 텍스트 |
| product_ids | array[string] | 필수 | - | 검색할 상품 ID 리스트 |
| index_name | string | 선택 | product_index_v3 | 인덱스 이름 |
| pipeline_id | string | 선택 | hybrid-minmax-pipeline | 파이프라인 ID |
| top_k | integer | 선택 | 3 | 반환할 결과 개수 (1-100) |

---

## 설정 및 환경 변수

### 환경 변수 (.env)

```bash
# OpenSearch 연결 설정 (비밀번호는 openssl rand -base64 24 로 생성)
OPENSEARCH_ADMIN_PASSWORD=CHANGE_ME_STRONG_RANDOM
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
# 검색 파이프라인 정의의 "combination" 블록 (`grep -n '"weights"' opensearch_hybrid.py`로 위치 확인)
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

## 프로젝트 구조

```
opensearch/
├── opensearch_api.py                   # FastAPI 서버 (8010)
├── opensearch_hybrid.py                # OpenSearch 하이브리드 검색 클라이언트
├── setup_opensearch.py                 # 인덱스 매핑 + 검색 파이프라인 셋업
├── run_indexing_pipeline.py            # v3 카테고리 색인 통합 실행 (skincare 선행)
├── index_products_skincare.py          # 카테고리별 색인 (skincare가 인덱스 생성)
├── index_products_color_tone.py        # 카테고리별 색인
├── index_products_hair.py              # 카테고리별 색인
├── index_products_living_supplies.py   # 카테고리별 색인
├── index_products_fragrance_body.py    # 카테고리별 색인
├── index_products_inner_beauty.py      # 카테고리별 색인
├── index_products_beauty_tool.py       # 카테고리별 색인
├── index_products_v4_multivector.py    # v4 멀티벡터(문장단위) 색인 — 1차 인덱스
├── index_forbidden_sentences.py        # 금칙 문장 색인 (품질검사 stage2)
├── index_forbidden.sh                  # 위 스크립트의 배포용 래퍼 (CI가 호출)
├── create_snapshot.sh                  # S3 스냅샷 생성 (일일 cron)
├── restore_or_skip.sh                  # 재해 복구 전용 — 1차 인덱스가 비었을 때만 복원
├── path_utils.py                       # 경로 유틸리티
├── docker-compose.yml                  # OpenSearch 3노드 + Dashboards + 검색 API
├── Dockerfile.opensearch               # nori 형태소 분석기 포함 이미지
├── Dockerfile.api                      # 검색 API 이미지
├── .env.example                        # 환경 변수 예시
├── requirements.txt                    # Python 패키지
└── README.md                           # 이 파일
```

---

## Docker 명령어

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

# 볼륨 포함 전체 삭제 (주의)
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
curl -X DELETE "localhost:9200/product_index_v3"
```

---

## 검색 원리

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

## 테스트

### 1. 간단한 검색 테스트

```bash
# Swagger UI에서 테스트
open http://localhost:8010/docs
```

### 2. cURL로 테스트

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

## 성능 최적화

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

## 트러블슈팅

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
curl -X GET "localhost:9200/product_index_v3/_stats?pretty"

# 매핑 확인
curl -X GET "localhost:9200/product_index_v3/_mapping?pretty"

# 인덱스 삭제 후 재색인 (운영 클러스터에서는 라이브 등록분이 소실됩니다)
curl -X DELETE "localhost:9200/product_index_v3"
python setup_opensearch.py
python run_indexing_pipeline.py
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

## AWS 배포

배포는 GitHub Actions가 자동으로 수행합니다. `main` 푸시 시 `database/`·`opensearch/` 코드가
tar.gz로 묶여 S3 deploy 버킷에 올라가고, SSM `send-command`로 EC2에 전개됩니다.

상세 절차는 [../infra/DEPLOYMENT_GUIDE.md](../infra/DEPLOYMENT_GUIDE.md)를 참조하세요.

AWS 환경과 로컬의 차이 두 가지를 알아두면 좋습니다.

| 항목 | 로컬 (docker-compose) | AWS |
|---|---|---|
| 클러스터 | 3노드, 보안 활성(HTTPS) → `OPENSEARCH_USE_SSL=true` | 단일노드, `plugins.security.disabled` 평문 HTTP → `OPENSEARCH_USE_SSL=false` |
| 검색 API | `fastapi-search` 컨테이너 1개 | 전용 EC2 ASG + 내부 NLB로 수평 확장 |

---

## 기여

이슈 및 풀 리퀘스트는 언제든 환영합니다.

---

## 문의

프로젝트 관련 문의사항은 이슈를 등록해주세요.
