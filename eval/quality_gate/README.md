# 메시지 품질 게이트 결함 주입 실험

AI IC 메시지 품질 게이트(1단계 금지어 · 2단계 임베딩 유사도 · 3단계 LLM 판정)를 **믿을 수 있는지** 재는 실험이다. 생성된 메시지의 품질을 재는 실험은 아니다.

- 원본 메시지와, 결함 한 곳만 다른 변형 쌍에서 게이트가 그 차이를 잡는지 본다.
- 정답은 평가자 밖의 기준에 묶는다: 식약처 적발 사례·가이드라인, 상품 DB, 조작 자체.
- 플랜(사전 등록 포함)은 SecondBrain vault `wiki/dev-tasks/message-quality-gate-defect-injection-plan-20260929.md`에 있다.

## 환경

- **Python 3.11:** `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe`. anaconda 기본 환경은 `jose` 충돌로 backend를 import하지 못한다.
- **로컬 도커:** DB API `:8020`, OpenSearch API `:8010`, Postgres.
- **DB:** `database/seed_products.py`로 채운다(1,034건). `scripts/setup_pipeline.py`로 채우면 `product_details`가 빈다.
- **DB API 이미지:** `sqlalchemy<2.1`로 빌드한다(`requirements.txt`에 버전 미고정).

## 실행 순서 (`--run main`)

| # | 명령 | LLM | 사람이 할 일 |
|---|---|---|---|
| 0 | `python verify_stage2.py` | 없음 | 모두 통과해야 진행한다(35차 기준점 5쌍, override 기대값, idx 29) |
| 1 | `python build_originals.py --run main --n 70` | 생성 70회 | — |
| 2 | `python llm_review.py run --run main` → `audit` → `python review_kit.py serve --run main`("확인 대상" 필터) → `review_kit.py compare` → `llm_review.py merge` | 원본 70 · 문구 126 (gpt-5.5) | **LLM 1차 검수 + 사람 확인**(2026-09-30 결정). 사람은 LLM이 X · 확신 낮음인 항목과 무작위 20%만 눈가림으로 채운다. merge 가 항목 단위로 사람 값 우선, 나머지 LLM 값을 검수 CSV에 기록(`label_source` 열) |
| 3 | (2에 포함) | — | 문구 모집단 `data/d1_phrases.csv`(`python data/build_d1_phrases.py`로 생성)는 LLM이 검수하고, LLM이 X · 확신 낮음인 문구만 사람이 "D1 문구" 탭에서 확인한다. `review_ok`가 비어 있으면 4가 멈춘다(merge 후 채워짐) |
| 4 | `python make_d1_set.py --run main` | 없음 | 틀 모음 · D1 문장 생성. 제외 문구와 사유가 출력된다 |
| 5 | `python run_d1.py --run main` | 없음 | D1 주 지표(문구 단독 1·2단계) |
| 6 | `python draft_d3.py --run main` | 원본당 1회 | `d3_table_draft.csv` 전수 검수 → `reviewed_usable(O/X)`를 채워 `d3_table.csv`로 저장 |
| 7 | `python make_variants.py --run main` | 없음 | D1 · D2 · D4 전수 검수, C_repl 20% 검수 |
| 8 | `python run_gate.py --run main` | 약 4,000회 | 기본 반복: low 5 · medium 3 · minimal 3, 원본 속 D1은 low 2 |
| 9 | `python analyze.py --run main` | 없음 | `report.md`. 헤드라인은 앞쪽 "사전 등록 주 결론"에서만 고른다 |

- **검수 도구 (`review_kit.py`):**
  - `serve`: 브라우저(http://127.0.0.1:8765)에서 버튼을 누르면 CSV에 바로 저장한다. 판정 초안은 보여 주지 않고 근거만 보여 준다. 시작할 때 두 CSV를 `result/<run>/review_backup/`에 백업한다. 엑셀에서 CSV를 열어 두면 저장이 막히므로 닫고 쓴다. LLM · 게이트 · DB 호출 없음.
  - `status`: 열별 빈 칸 수.
  - `compare`: 두 번째 검수(`result/<run>/review_second/`에 같은 형식의 CSV 두 개)와의 열별 일치율 · Cohen's κ · 불일치 목록 → `result/<run>/review_agreement.md`.
  - 근거 텍스트 `data/enforcement_text/`는 vault `raw/`의 보도자료 13건 · 지침 · 별표 5 PDF에서 뽑은 것이다.
- **시범 재실행:** 본 실행 전에 원본 5건과 화장품 원본 보충분으로 1~9를 한 번 돌린다(`--run pilot2`).
- **멈춤 규칙:** 아래 중 하나라도 나오면 원인을 고치고 시범을 다시 돌린다.
  - 헤드라인 결함(D1 · D2 · D4)에서 라벨 오류가 하나라도 나온 경우. D3(보조로 사전 강등)는 라벨 오류가 난 케이스만 빼고 진행한다(전수 검수는 유지)
  - 보고서 "멈춤 규칙 확인"에서 불일치가 나온 경우
- **LLM 없이 1·2단계만 확인:** `run_gate.py --no-judge`

## 결과 폴더

- `result/pilot/`: 2026-09-29 첫 시범(원본 5건, 옛 변형 방식). 인용하지 않는다.
- `result/pilot2/`: 시범 2회차(D2·D3·D4, 원본 5건, low 2회, 검수는 어시스턴트). 인용하지 않는다.
- `result/smoke/`: 새 스크립트 스모크 확인용. `d1_phrases_smoke.csv`는 검토 예시 문장이라 **정답 근거가 아니다.** 인용하지 않는다.
