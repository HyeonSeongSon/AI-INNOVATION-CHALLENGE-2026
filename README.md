# AI Innovation Challenge 2026

**페르소나 기반 뷰티 상품 추천 및 CRM 메시지 자동 생성 시스템**

[![CI - Deploy](https://github.com/HyeonSeongSon/AI-INNOVATION-CHALLENGE-2026/actions/workflows/deploy.yml/badge.svg)](https://github.com/HyeonSeongSon/AI-INNOVATION-CHALLENGE-2026/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![OpenSearch](https://img.shields.io/badge/OpenSearch-005EB8?logo=opensearch&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

사용자가 채팅으로 "특정 페르소나에게 어떤 상품의 홍보 메시지를 만들어줘"라고 요청하면,
LangGraph 멀티에이전트 백엔드가 ① 요청을 분석·라우팅하고 ② OpenSearch 하이브리드 검색으로
페르소나에 맞는 상품을 추천하며 ③ 마케팅 메시지를 생성하고 ④ 3단계 품질 검사를 통과한
메시지만 저장합니다. 응답은 SSE(Server-Sent Events)로 실시간 스트리밍됩니다.

## 목차

- [주요 기능](#주요-기능)
- [문서 안내](#문서-안내)
- [기술 스택](#기술-스택)
- [시스템 아키텍처](#시스템-아키텍처)
- [빠른 시작 (로컬 Docker Compose)](#빠른-시작-로컬-docker-compose)
- [API 엔드포인트](#api-엔드포인트)
- [프로젝트 구조](#프로젝트-구조)
- [주요 워크플로우](#주요-워크플로우)
- [테스트 & 평가](#테스트--평가)
- [개발 가이드](#개발-가이드)

---

## 주요 기능

- **페르소나 기반 상품 추천** — 멀티벡터 retrieval + 페르소나 3차원(need/preference/persona) 병렬 하이브리드 검색을 **RRF(Reciprocal Rank Fusion)**로 융합하여 top-3 추천
- **하이브리드 검색** — OpenSearch BM25(nori 한국어 형태소) + KNN(`KURE-v1` 임베딩) 결합
- **CRM 메시지 생성** — LangGraph 멀티에이전트(Supervisor 패턴) 기반 자동 생성
- **3단계 품질 검사** — Rule(길이·금칙어) → Semantic 유사도(KNN) → LLM-as-a-Judge, 실패 시 피드백 재생성
- **데이터 등록 파이프라인** — 페르소나·상품을 텍스트/파일로 등록(백그라운드 잡 + SSE 진행 스트리밍)
- **인증/보안** — JWT(HttpOnly Cookie) + 서비스 간 `INTERNAL_TOKEN` + 단명 User Assertion JWT, PostgreSQL 기반 Rate Limiter
- **실시간 스트리밍** — `/chat/v2/stream` SSE로 노드 진행 상황·토큰·결과를 점진 전달

---

## 문서 안내

| 문서 | 내용 |
|------|------|
| **[README.detailed.md](README.detailed.md)** | 전체 아키텍처·백엔드/DB/검색/프론트 구조·요청 흐름·프로덕션 인프라·CI/CD 상세 (가장 상세한 레퍼런스) |
| [CLAUDE.md](CLAUDE.md) | 코딩 가이드라인 및 프로덕션 코드 패턴 |
| [infra/DEPLOYMENT_GUIDE.md](infra/DEPLOYMENT_GUIDE.md) | AWS 배포 런북 (0에서 운영 배포까지, GitHub Actions 자동 배포) |
| [infra/USER_CREATION_GUIDE.md](infra/USER_CREATION_GUIDE.md) | 배포 환경 admin/일반 유저 계정 생성 방법 |
| [database/SETUP_GUIDE.md](database/SETUP_GUIDE.md) | DB 초기화 및 데이터 색인 가이드 |
| [opensearch/README.md](opensearch/README.md) | OpenSearch 하이브리드 검색 시스템 상세 |
| [loadtest/README.md](loadtest/README.md) | `/chat/v2/stream` 동시성 게이팅 부하테스트 |

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.11 (백엔드/DB/검색), JavaScript (프론트엔드) |
| 백엔드 | FastAPI, LangGraph, LangChain, A2A(Agent-to-Agent) 커스텀 프로토콜 |
| LLM | OpenAI(`gpt-5-mini` / `gpt-5-nano` 기본값), Anthropic Claude·Google Gemini 선택 (`ALLOWED_MODEL_PREFIXES` 화이트리스트) |
| 임베딩 | `nlpai-lab/KURE-v1` (SentenceTransformer, 한국어) |
| 벡터 검색 | OpenSearch (BM25 + KNN 하이브리드, nori 형태소 분석) |
| RDB | PostgreSQL 14+ (SQLAlchemy 2.0 ORM) |
| 체크포인터 | LangGraph `AsyncPostgresSaver` (PostgreSQL) |
| 인증 | JWT(HttpOnly Cookie) + `INTERNAL_TOKEN` + User Assertion JWT |
| 프론트엔드 | React 19, Vite 7, React Router 7, styled-components, axios |
| 관측성 | structlog(JSON 구조화 로그), LangSmith 트레이싱(선택) |
| 인프라(프로덕션) | AWS — CloudFront+S3(프론트), ALB+ECS Fargate(앱 5종), EC2(DB/OpenSearch/OpenSearch API), Terraform, GitHub Actions OIDC |
| 인프라(로컬) | Docker Compose(모듈별) + Nginx(프론트 정적 서빙) |

---

## 시스템 아키텍처

논리적으로 **5개의 FastAPI 마이크로서비스**(API Gateway·CRM·Recommend·Generate·Data
Registration) + **DB API** + **OpenSearch API**로 구성됩니다.

| 서비스 | 포트 | 진입점 | 노출 |
|--------|------|--------|------|
| API Gateway (Auth + BFF Proxy) | 8005 | `backend/main.py` | **외부 공개** |
| CRM Service (Supervisor 오케스트레이터) | 8006 | `backend/servers/crm_server.py` | 내부 |
| Recommend Agent | 8001 | `backend/servers/recommend_server.py` | 내부 |
| Generate Agent | 8002 | `backend/servers/generate_server.py` | 내부 |
| Data Registration Agent | 8003 | `backend/servers/data_registration_server.py` | 내부 |
| Database API | 8020 | `database/api_server.py` | 내부 |
| OpenSearch API | 8010 | `opensearch/opensearch_api.py` | 내부 |
| Frontend | 3000 | `frontend/` | 외부 공개 |

```
┌──────────────┐
│   Client     │  (SSE 스트리밍)
└──────┬───────┘
       ▼
┌─────────────────────────────────────────────────────────┐
│  API Gateway :8005  (JWT 인증 · Rate Limit · BFF 프록시)  │
└──────┬───────────────────────────────────┬──────────────┘
       │ X-Internal-Token + X-User-Assertion│ (DB 프록시)
       ▼                                     ▼
┌─────────────────────────────┐      ┌────────────────────┐
│  CRM Service :8006          │      │  Database API :8020│
│  (Supervisor 오케스트레이터) │◄────►│  (PostgreSQL)      │
│    │ A2A                    │      └────────────────────┘
│    ├─ Recommend Agent :8001 │
│    ├─ Generate Agent  :8002 │─────►┌────────────────────┐
│    └─ Data Reg Agent  :8003 │      │  OpenSearch API    │
└─────────────────────────────┘      │  :8010 → 엔진 :9200 │
                                      └────────────────────┘
```

> **로컬**: 4개 Docker Compose 스택이 `msa-net` 브리지 네트워크에서 컨테이너명으로 통신하며,
> 외부 노출은 Gateway(8005)·Frontend(3000)뿐입니다.
> **프로덕션(AWS)**: 앱 5종은 ECS Fargate(Cloud Map DNS), DB·OpenSearch는 EC2, 진입점은
> CloudFront 하나입니다. 상세는 [README.detailed.md](README.detailed.md) 2·11장 참고.

---

## 빠른 시작 (로컬 Docker Compose)

### 1. 사전 요구사항

- Docker & Docker Compose
- Python 3.11
- OpenAI API Key (또는 Anthropic/Google — 사용하는 모델에 따라)

### 2. 환경 변수 설정

각 모듈의 `.env.example`을 복사하여 `.env`를 만들고 값을 채웁니다.

```bash
cp backend/app/.env.example backend/app/.env   # OPENAI_API_KEY, INTERNAL_TOKEN, JWT_SECRET 등
cp database/.env.example    database/.env       # POSTGRES_*, INTERNAL_TOKEN
cp opensearch/.env.example  opensearch/.env     # OPENSEARCH_ADMIN_PASSWORD, INTERNAL_TOKEN
cp frontend/.env.example    frontend/.env       # VITE_AUTH_API_URL, VITE_API_URL
```

> ⚠️ `INTERNAL_TOKEN`은 backend / database / opensearch에서 **동일한 값**이어야 하고,
> `JWT_SECRET`과는 **다른 값**이어야 합니다 (`openssl rand -hex 32`로 각각 생성).
> 필수 시크릿은 서버 시작 시 `Settings.validate_required_secrets()`가 검증합니다(fail-fast).

### 3. 전체 스택 실행

```bash
docker network create msa-net          # 최초 1회 (백엔드 compose가 external network 사용)

# OpenSearch — 엔진/검색 API 기동 후 인덱스·색인
cd opensearch && docker compose up -d
python setup_opensearch.py             # 인덱스/검색 파이프라인 셋업
python run_indexing_pipeline.py        # v3 상품 색인 (skincare가 인덱스 생성)
python index_products_v4_multivector.py # v4 멀티벡터(문장단위 5필드) 색인
python index_forbidden_sentences.py    # 품질검사용 금칙 문장 색인

# Database — PostgreSQL/pgAdmin/DB API 기동 후 스키마·시드
cd ../database && docker compose up -d
python scripts/setup_pipeline.py       # 테이블 생성 + 초기 데이터 적재

# Backend — 5개 마이크로서비스
cd ../backend && docker compose up
```

기동되는 서비스:

- **API Gateway**: http://localhost:8005
- **Frontend**: http://localhost:3000
- **Database API**: http://localhost:8020
- **OpenSearch API**: http://localhost:8010
- **OpenSearch Dashboards**: http://localhost:5601
- **pgAdmin**: http://localhost:5050

> 개별 uvicorn 실행, LangGraph Studio 디버깅 등 개발용 실행 방법은
> [README.detailed.md](README.detailed.md) 14장을 참고하세요.

---

## API 엔드포인트

### API Gateway (8005) — 외부 노출

| 메서드 | 경로 | 역할 | 인증 |
|--------|------|------|------|
| POST | `/auth/register` | 회원가입(bcrypt) | Rate Limit |
| POST | `/auth/login` | 로그인 → HttpOnly 쿠키 발급 | Rate Limit + 계정잠금 |
| POST | `/auth/refresh` | access/refresh 토큰 회전 | refresh 쿠키 |
| POST | `/auth/logout` | 토큰 폐기 + 쿠키 삭제 | — |
| GET | `/auth/me` | 내 정보 조회 | access 쿠키 |
| POST | `/auth/admin/users` | admin이 사용자 생성 | **admin** |
| POST | `/api/marketing/chat/v2` | CRM 메시지 생성 (단건 JSON) | JWT + chat Rate Limit |
| POST | `/api/marketing/chat/v2/stream` | CRM 메시지 생성 (SSE 스트리밍) | JWT + chat Rate Limit |
| POST | `/api/pipeline/personas/create-from-text` | 텍스트 페르소나 생성 | JWT |
| POST | `/api/pipeline/personas/create-from-file/upload` | 파일 페르소나 업로드 → job_id | JWT |
| GET | `/api/pipeline/personas/jobs/{id}/stream` | 업로드 진행 SSE | JWT |
| POST | `/api/pipeline/products/register/upload` | 상품 업로드 | **admin** |
| GET/POST/PUT/DELETE | `/api/conversations*` | 대화 CRUD → DB 프록시 | JWT |
| GET | `/api/generated-messages*` | 생성 메시지 조회 → DB 프록시 | JWT |
| GET | `/health` | DB·CRM·internal 클라이언트 상태 | — |

**SSE 이벤트 타입**: `node_start` / `token` / `text_chunk` / `text_done` / `log` /
`node_end` / `result` / `error` / `done`

> 내부 서비스(CRM 8006 / DB API 8020 / OpenSearch API 8010)의 엔드포인트 상세는
> [README.detailed.md](README.detailed.md) 4·5·6장을 참고하세요.

---

## 프로젝트 구조

```
AI-INNOVATION-CHALLENGE-2026/
├── backend/                      # FastAPI 백엔드 (5개 마이크로서비스)
│   ├── main.py                   # API Gateway (port 8005)
│   ├── servers/                  # 각 서비스 진입점 (8001/8002/8003/8006)
│   ├── a2a/                      # Agent-to-Agent 내부 통신 프로토콜
│   └── app/
│       ├── api/                  # API 라우터 (auth, crm_proxy, db_proxy, *_pipeline 등)
│       ├── agents/               # LangGraph 에이전트 (crm/recommend/generate/data_reg)
│       ├── core/                 # 인프라 (auth, logging, llm_factory, rate_limiter 등)
│       └── config/settings.py    # 환경변수 중앙 관리 + 시작 시 검증
├── database/                     # PostgreSQL + Database API (port 8020)
│   ├── api_server.py             # Database API 진입점
│   ├── routers/                  # API 라우터 (personas, products, conversations 등)
│   ├── core/                     # ORM 모델, DB 설정
│   ├── init/                     # 초기화 SQL (01~07)
│   ├── migrations/               # Alembic 마이그레이션
│   └── scripts/setup_pipeline.py # DB 초기화 스크립트
├── opensearch/                   # OpenSearch + 검색 API (port 8010)
│   ├── opensearch_api.py         # OpenSearch API 진입점
│   ├── opensearch_hybrid.py      # 하이브리드 검색 클라이언트 (KURE-v1, RRF 파이프라인)
│   ├── setup_opensearch.py       # 인덱스/파이프라인 초기화
│   └── index_products_*.py       # 카테고리별 / v4 멀티벡터 색인 스크립트
├── frontend/                     # React 19 + Vite 7 (port 3000)
│   └── src/                      # 컴포넌트, 페이지, Context (Auth/Chat/Toast)
├── infra/                        # 프로덕션 AWS 인프라 (Terraform)
│   ├── bootstrap/                # state·OIDC·ECR
│   └── ec2/                      # VPC·ALB·ECS·EC2·Secrets 등 운영 인프라
├── loadtest/                     # 부하테스트 스크립트/결과
└── .github/workflows/            # CI/CD (deploy.yml, snapshot.yml)
```

---

## 주요 워크플로우

### CRM 메시지 생성 (SSE)

```
POST /api/marketing/chat/v2/stream
    ↓
[Gateway :8005] JWT 인증 + chat Rate Limit → X-User-Assertion 발급 → CRM 릴레이
    ↓
[CRM Supervisor :8006] maybe_summarize → supervisor_agent
  LLM(with_structured_output)이 task_plan(에이전트 실행 순서)을 한 번에 결정
    ↓
[Recommend Agent :8001]  (A2A)
  검색 쿼리 조회/생성 → OpenSearch 하이브리드 검색
  → 멀티벡터 retrieval(top-100) → 3차원 병렬 검색 → RRF 융합 → top-3
    ↓
[Generate Agent :8002]  (A2A)
  메시지 생성 → 3단계 품질 검사(Rule → Semantic → LLM Judge)
  → 실패 시 피드백 재생성 루프
    ↓
[CRM Supervisor] 최종 응답 조합 → SSE(token/text_chunk/result/done)
    ↓
[저장] conversation_messages + generated_messages(품질 통과분) — best-effort
```

> 단계별 상세와 프로덕션(AWS) 경로 차이는 [README.detailed.md](README.detailed.md) 8·11장 참고.

---

## 테스트 & 평가

추천 품질과 프로덕션 부하 안정성을 **정량 지표로 검증**했습니다. 특히 추천은 *"잘 되는지 판단할 기준 자체가 없다"* 는 문제에서 출발해, **정답이 명확한 검색 지표**와 **실사용에 가까운 LLM 채점**이라는 두 축으로 평가 체계를 직접 설계했습니다.

### 1. 검색 품질 평가 — 상품 역추적 (Hit@3 · MRR)

정답을 명확히 만들기 위해 **상품을 먼저 정하고, 그 상품을 살 법한 페르소나를 역생성**한 뒤, 해당 페르소나로 검색했을 때 원래 상품이 상위에 오르는지를 측정했습니다. 정답이 분명해 검색 파이프라인 개선을 객관적으로 추적할 수 있습니다.

- **평가 스크립트**: [`eval/run_eval.py`](eval/run_eval.py) — Retrieval Hit@100 → 3차원 RRF top-N → Hit@N / Recall@N / MRR
- **Retrieval Hit@100**: 정답이 1차 검색에서 아예 누락되는지를 진단하는 **하한선** 지표

| 지표 | 개선 전 | **개선 후** |
|------|:---:|:---:|
| **Hit@3** | 0.33 | **0.85** |
| **MRR** | 0.29 | **0.72** |
| **Retrieval Hit@100** (1차 검색 재현율) | — | **100%** |

이 지표를 근거로 **BM25 + 벡터를 RRF로 융합한 하이브리드 검색**, **멀티벡터 인덱스**, **페르소나 다관점 쿼리 확장**을 도입해 개선을 확정했습니다.

### 2. 추천 품질 평가 — LLM-as-Judge + 평가자 간 일치도

역생성 페르소나는 상품 정보에서 파생된 만큼 실제 사용자의 표현과 다를 수 있어, 검색 지표를 곧 추천 품질로 볼 수는 없다고 판단했습니다. 그래서 **상품과 무관하게 랜덤 생성한 페르소나**에 대한 추천 적합도를 LLM이 1~5점으로 채점하는 평가를 추가했습니다.

정답이 없다는 한계를 보완하기 위해, **동일한 결과를 3명이 독립적으로 평가**하고 평가자 간 일치도를 측정해 **채점을 신뢰할 기준선**부터 확립했습니다.

- **평가셋**: 사람이 주석한 60개 페르소나 (`eval/human_annotated_eval_data_set.jsonl`)
- **일치도 분석**: [`eval/human_annotated/analyze_annotations.py`](eval/human_annotated/analyze_annotations.py) — Fleiss' Kappa · Gwet's AC1 · Krippendorff's Alpha

| 평가자 간 일치도 | 값 |
|------|:---:|
| 완전 합의율 (3인 일치) | **87.9%** |
| Fleiss' Kappa | **0.64** (유의미한 일치) |

이 기준선 위에서 임베딩 가중치와 top-k를 반복 실험하되, **평균 점수가 아니라 상위 순위일수록 적합도가 높아지는 정렬 품질**을 기준으로 최적 조합을 선택했습니다. 최종 채택 조합(`k=10`, weight_v4)은 전체 평균이 가장 높으면서 **rank1–rank5 격차도 가장 크게** 벌어졌습니다.

| 지표 | 초기 | 튜닝 중 | **최종 채택 (k=10, v4)** |
|------|:---:|:---:|:---:|
| **top-5 평균** | 3.634 | 3.662 | **3.694** |
| top-3 평균 | 3.961 | 3.867 | **3.939** |
| rank1 평균 | 4.083 | 4.067 | **4.167** |
| **rank1–rank5 격차** (정렬 품질) | +0.999 | +0.863 | **+1.031** |
| rank1–rank3 격차 | +0.133 | +0.250 | **+0.350** |

> 평균만 보면 차이가 작지만, 최종 조합은 **상위 순위일수록 점수가 단조 상승**하도록 정렬 품질을 끌어올린 것이 핵심입니다 (`gpt-5-mini` judge, N=60).

```bash
# 검색 품질 평가 (Hit@3 · MRR · Retrieval Hit@100)
python eval/run_eval.py

# 추천 가중치 LLM-as-Judge 평가
python eval/eval_recommendation_weights_v3.py

# 평가자 간 일치도 (Fleiss' Kappa · Gwet's AC1)
python eval/human_annotated/analyze_annotations.py
```

### 3. 부하 테스트 (동시 100 사용자)

`/api/marketing/chat/v2/stream` SSE 엔드포인트에 대해 **동시 100명 완료율 100%**를 목표로 18~39차(22회) 반복 검증했습니다. 상세는 [loadtest/README.md](loadtest/README.md) 참고.

| 항목 | 결과 |
|------|------|
| 목표 | 동시 100명 `/chat/v2/stream` 요청 완료율 100% |
| 최종(39차) | **완료율 100%**, p50 **202.5s** / p99 **323.3s** |
| 진행 | 0% → 63% → 87% → 100% (매 라운드 가설→실측→원인확정→재검증) |
| 방법 | VPC 내부 전용 EC2에서 부하 생성 (단일 클라이언트는 동시 220+에서 자체 붕괴) |
| 도구화 | `parse_results.py`(SSE 분류) → `fetch_metrics.py`(CloudWatch 수집) → `analyze_results.py`(PASS/FAIL 표) |

단계적으로 이동한 병목을 순차 제거했습니다 — OpenSearch 동시성 → 타임아웃 계층 역전 → 인스턴스 용량 → 임베딩 중복 호출 → SSE 데드라인 → LLM 레이트리밋 → 구조적 LLM 호출 보호(재시도+세마포어 9곳 일괄 적용).

```bash
# 부하 테스트 실행 (VPC 내부 EC2에서)
loadtest/run_chat_stream_test.sh
python loadtest/analyze_results.py <result_dir> <metrics_json>
```

---

## 개발 가이드

### 브랜치 전략

개인 작업은 각자 브랜치에서 진행하고, `main`에는 병합된 최종 결과물만 올립니다.
`main` 푸시 시 GitHub Actions(`deploy.yml`)가 AWS로 전자동 배포합니다.

```bash
git checkout -b feature/your-feature-name
# 작업 후
git commit -m "feat: your feature description"
git checkout main && git merge feature/your-feature-name
git push origin main   # → CI/CD 트리거
```

### 코딩 가이드라인

타입 안전성·비동기 일관성·에러 처리·LangGraph 노드 설계 등 프로덕션 코드 패턴은
[CLAUDE.md](CLAUDE.md)에 정리되어 있습니다.

---

## 라이선스

MIT License

## 문의

프로젝트 관련 문의사항은 이슈를 생성해주세요.
