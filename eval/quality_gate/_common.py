"""
eval/quality_gate 공통 부트스트랩 — 경로·환경변수·데이터 로딩·2단계 전수 점수.

호스트에서 로컬 도커(DB API :8020, OpenSearch API :8010)에 붙어 실제 게이트 코드를 돌린다.
backend/app/.env 의 서비스 호스트명(fastapi-search, ai-innovation-db-api)은 호스트에서
풀리지 않으므로, settings 를 import 하기 전에 localhost 로 덮어쓴다(pydantic-settings 는
환경변수를 .env 보다 우선한다).

backend 코드 일부가 `from app.core...` 절대 import 를 쓰므로, 모듈이 `backend.app.*` 와
`app.*` 두 이름으로 중복 로드되지 않게 이 패키지는 전부 `app.*` 경로로 import 한다.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BASE_DIR = Path(__file__).resolve().parent
RESULT_ROOT = BASE_DIR / "result"

PERSONA_FILE = REPO_ROOT / "eval" / "human_annotated" / "human_annotated_eval_data_set.jsonl"
PERSONA_SPEC_FILE = REPO_ROOT / "eval" / "human_annotated" / "result" / "persona_specs.json"

LOCAL_OVERRIDES = {
    "OPENSEARCH_API_URL": "http://localhost:8010",
    "DATABASE_API_URL": "http://localhost:8020",
    "POSTGRES_HOST": "localhost",
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_TRACING": "false",
}

# 게이트 2단계와 같은 문장 분리 정규식 (quality_check.py _run_semantic_similarity_check)
GATE_SENTENCE_SPLIT = r"[.!?。！？\n]+"


def bootstrap() -> None:
    """sys.path · 환경변수 · .env 로드. backend 모듈 import 전에 한 번 호출한다."""
    for key, value in LOCAL_OVERRIDES.items():
        os.environ[key] = value
    for p in (str(BACKEND_DIR), str(REPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / "app" / ".env")  # override=False → 위 덮어쓰기 유지, OPENAI_API_KEY 등 주입
    sys.stdout.reconfigure(encoding="utf-8")

    from app.core.logging import configure_logging

    configure_logging(log_level="WARNING", json_output=False, environment="development")


def run_dir(run: str) -> Path:
    path = RESULT_ROOT / run
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_personas() -> dict[str, dict[str, Any]]:
    """평가용 페르소나 60명 + 추출 스펙. persona_id → {information, product_tag, spec}."""
    specs = json.loads(PERSONA_SPEC_FILE.read_text(encoding="utf-8"))
    personas = {}
    for row in load_jsonl(PERSONA_FILE):
        pid = row["persona_id"]
        personas[pid] = {**row, "spec": specs.get(pid, {}).get("spec", {})}
    return personas


def persona_info(persona: dict[str, Any]) -> dict[str, Any]:
    """생성기·판정기에 넘기는 페르소나 dict.

    평가용 60명은 DB personas 테이블에 없는 자유 서술이라 PersonaClient 대신 직접 넘긴다
    (두 서비스 모두 persona_info dict 를 그대로 JSON 으로 프롬프트에 넣는다).
    """
    return {"persona_id": persona["persona_id"], "페르소나 정보": persona["information"]}


def gate_sentences(title: str, message: str) -> list[str]:
    """게이트 2단계와 같은 방식으로 문장 분리."""
    full_text = f"{title} {message}".strip()
    return [s.strip() for s in re.split(GATE_SENTENCE_SPLIT, full_text) if s.strip()]


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """본문을 종결부호 포함 문장 단위 (start, end) 구간으로 나눈다 — 삽입·삭제 위치 계산용."""
    return [m.span() for m in re.finditer(r"[^.!?。！？\n]+[.!?。！？]*", text) if m.group().strip()]


async def stage2_topk(http_client, sentences: list[str], top_k: int) -> list[list[dict[str, Any]]]:
    """게이트와 같은 배치 엔드포인트로 문장별 상위 top_k 결과(점수 내림차순)를 구한다.

    top_k=3 은 게이트와 같은 ANN 경로, top_k=100 은 색인 문장 87개 전체를 후보로 보는 전수
    최근접이다(2026-09-29 컨테이너 내부 전수 계산으로 확인). 2위 이하 매칭 점수가 필요할 때
    (35차 idx 69 의 0.858 은 2위 매칭) 이 함수를 쓴다.
    """
    from app.config.settings import settings

    response = await http_client.post(
        f"{settings.opensearch_api_url}/api/search/similar-sentences/batch",
        json={
            "index_name": settings.opensearch_forbidden_sentences_index,
            "queries": sentences,
            "top_k": top_k,
        },
    )
    response.raise_for_status()
    return [
        sorted(({"score": r.get("score", 0.0), "sentence": r.get("sentence")} for r in item["results"]),
               key=lambda r: -r["score"])
        for item in response.json()["results"]
    ]


async def stage2_exact_top1(http_client, sentences: list[str]) -> list[dict[str, Any]]:
    """문장별 전수 최근접 1위(점수 · 매칭 문장). 2단계 주 판정(전수 기준)에 쓴다."""
    out = []
    for results in await stage2_topk(http_client, sentences, 100):
        top = results[0] if results else {}
        out.append({"score": top.get("score", 0.0), "matched": top.get("sentence")})
    return out


async def stage2_ann_top1(http_client, sentences: list[str]) -> list[dict[str, Any]]:
    """문장별 ANN(k=3, 게이트와 같은 경로) 1위. 2단계 보조 판정(실제 검색 방식 기준)에 쓴다."""
    from app.config.settings import settings

    out = []
    for results in await stage2_topk(http_client, sentences, settings.quality_check_semantic_top_k):
        top = results[0] if results else {}
        out.append({"score": top.get("score", 0.0), "matched": top.get("sentence")})
    return out


# ── 변형 · D1 문장 공통 도구 ──────────────────────────────────────────────────

# CTA(행동 유도) 문장 판별. 시범의 마커("담아", "확인")는 "철학을 담아" · "확인했습니다" 같은
# 사실 서술에도 걸려 D4 라벨을 틀리게 만들었다(wiki/errors/quality-gate-pilot-variant-label-errors-20260929.md).
# 판매·클릭·다음 행동을 권하는 표현만 잡고, D4 는 어차피 전수 검수한다.
CTA_RE = re.compile(
    r"(보세요|보실래요|보시겠어요|볼까요|보기|보러|바로\s?가기|클릭|구매하|구매해|장바구니|신청하|신청해|참여하|참여해|"
    r"눌러|받아\s?보|받아\s?가|만나\s?보|알아\s?보|확인해\s?보|확인하세요|확인하기|확인해\s?주세요|주문하|예약하|담아\s?보|"
    r"놓치지\s?마세요|서두르세요)"
)


# 문장 끝 명령 · 권유형 — 시범 2회차 O004 "지금 41% 할인, 샴푸 후 1분으로 모근부터 케어하세요"를 CTA_RE 가
# 놓쳐 D4 에 CTA 가 남았다. "CTA 전부 삭제"는 덜 지우는 쪽보다 더 지우는 쪽이 라벨에 안전하다(D4 는 전수 검수).
CTA_END_RE = re.compile(r"(세요|십시오|보실래요|할까요|해요)\s*[.!?。！？]*\s*$")


def is_cta(sentence: str) -> bool:
    return bool(CTA_RE.search(sentence) or CTA_END_RE.search(sentence.strip()))


def is_decimal_fragment(sentence: str, text: str) -> bool:
    """게이트 문장 분리가 소수점에서 자른 조각인가 — "평점 4.5"가 "평점 4" · "5…"로 갈린다.
    이런 조각을 치환 자리나 틀로 쓰면 메시지가 깨진다."""
    pos = text.find(sentence)
    if pos < 0:
        return False
    end = pos + len(sentence)
    starts_after_point = pos >= 2 and text[pos - 1] == "." and text[pos - 2].isdigit() and sentence[:1].isdigit()
    ends_before_point = end + 1 < len(text) and text[end] == "." and text[end + 1].isdigit() and sentence[-1:].isdigit()
    return starts_after_point or ends_before_point


def fix_josa(text: str, start: int, end: int) -> str:
    """text[start:end] 를 새 낱말로 바꾼 뒤, 바로 뒤 조사(은/는 · 이/가 · 을/를 · 과/와)를 받침에 맞춘다."""
    word = text[start:end].rstrip("™®").strip()
    last = word[-1:] if word else ""
    if "가" <= last <= "힣":
        batchim = (ord(last) - 0xAC00) % 28 != 0
    elif last.isdigit():
        batchim = last in "013678"
    else:
        batchim = last.upper() in "LMNR"
    pairs = {"은": "는", "는": "은", "이": "가", "가": "이", "을": "를", "를": "을", "과": "와", "와": "과"}
    want = {"은": batchim, "이": batchim, "을": batchim, "과": batchim,
            "는": not batchim, "가": not batchim, "를": not batchim, "와": not batchim}
    j = text[end:end + 1]
    if j in pairs and not want[j]:
        text = text[:end] + pairs[j] + text[end + 1:]
    return text


def nospace(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def topic_josa(word: str) -> str:
    """주제 조사 은/는 — 마지막 글자의 받침으로 고른다(한글이 아니면 숫자·영문 읽기로 근사)."""
    last = (word or "").strip()[-1:] or "는"
    if "가" <= last <= "힣":
        return "은" if (ord(last) - 0xAC00) % 28 else "는"
    if last.isdigit():
        return "은" if last in "013678" else "는"
    return "은" if last.upper() in "LMNR" else "는"


def short_name(product_name: str, text: str) -> str | None:
    """생성 메시지가 실제로 쓴 상품 짧은 이름 — DB product_name 의 연속 토큰 중 메시지에 나오는 가장 긴 것.

    DB product_name 은 검색용 긴 문자열이라 문장 틀에 쓰지 않는다(플랜 "문장 틀").
    """
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", product_name or "")
    tokens = [t for t in name.split() if t]
    best = None
    for i in range(len(tokens)):
        for j in range(len(tokens), i, -1):
            cand = " ".join(tokens[i:j])
            if len(nospace(cand)) >= 2 and cand in text and (best is None or len(cand) > len(best)):
                best = cand
                break
    return best


def judge_visible_text(product_flat: dict[str, Any]) -> str:
    """판정기에 보이는 23개 필드(_JUDGE_PRODUCT_FIELDS)의 값을 공백 없이 이어 붙인 문자열 — "DB에 없음" 검사용."""
    from app.agents.generate_message_agent.prompts.quality_check_prompt import _JUDGE_PRODUCT_FIELDS

    parts = []
    for key in _JUDGE_PRODUCT_FIELDS:
        value = product_flat.get(key)
        if value in (None, "", [], {}):
            continue
        parts.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    return nospace(" ".join(parts))
