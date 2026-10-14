"""
메시지 생성기 근거 개선 — 지표 측정 (사전 등록 파일, baseline_hashes.json 으로 잠근다).

메시지 하나마다 같은 방식으로 잰다(수정 전 · 후 모두):
    1. LLM 근거 검증 (주 지표): gpt-5.5 날짜 고정 스냅숏(llm_review.call 재사용, SDK 직접 호출).
       입력: 상품정보(제외 필드를 뺀 스냅숏, product_name · brand 포함) · 브랜드 프로필 · 페르소나 · 메시지 · GROUNDING_DEF.
       출력: 근거 없는 주장(구간 · 유형 · DB 판정 · 출처 · 가장 가까운 DB 문구) · 근거 있는 주장 · purpose_conveyed.
       후처리: 구간이 메시지에 실제로 있는지 확인. DB 판정이 '없음'인데 구간의 숫자가 모두 상품정보에 있고
       핵심어(2자 이상 명사)의 80% 이상이 상품정보에 있으면 '자동 재검토'.
       메시지 판정: 양성(자동 재검토가 아닌 근거 없음 ≥1) · 재검토(근거 없음이 모두 자동 재검토) · 음성.
       LLM 만으로 낸 주 지표는 재검토를 양성으로 센다.
    2. 정규식 지표 (교차 확인용, 판정은 LLM 과 사람): 근거 없는 날짜 · 시험 · 판매인기 · 변화 · 검증 표현,
       브랜드 사실 표현, 슬로건 키워드, DB 등록 시각 날짜(점검 항목).
    3. 회귀: 판정기 3단계 low(run_gate.judge 본문 복사 — run_gate import 는 검색 함수를 바꿔 끼우는 부작용이 있다),
       형식(제목 40자 · 본문 350자 · JSON), 마지막 CTA, 1단계 금지어.
측정 정의 값(POPULARITY_MIN_REVIEWS · GENERATION_EXCLUDED_FIELDS)이 PREREG.md 와 다르면 중단한다.
결과마다 사전 등록 파일 · 게이트 파일 해시와 AMENDMENTS 상태를 기록한다.

사용법:
    python measure.py --set holdout --tag before --judge-runs 2
    python measure.py --set insample --tag after --judge-runs 1 --skip-verifier
    python measure.py --messages result/pilot/messages.jsonl --out result/pilot   # 잠금 전 검증기 시험
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gg_common as gg
from gg_common import load_jsonl, write_jsonl

import build_originals as bo  # noqa: E402  (kiwi 명사)
import llm_review  # noqa: E402  (gpt-5.5 호출 · 재시도)
import review_kit  # noqa: E402  (문장 분리)
import run_d1  # noqa: E402  (1단계 검출기, 네트워크 없음)
from _common import is_cta  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.data_loader import get_brand_tones  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402

import grounding_def as gd  # noqa: E402
from app.agents.generate_message_agent.prompts.product_fields import generation_product_info  # noqa: E402

SCORE_KEYS = ("accuracy", "tone", "personalization", "naturalness", "cta_clarity")
VERIFIER_CONCURRENCY = 6
JUDGE_CONCURRENCY = 8
AUTO_REVIEW_NOUN_RATIO = 0.8
TITLE_MAX, BODY_MAX = 40, 350
LABEL_WORDS = {"신제품 홍보": ("신제품", "NEW", "New", "new", "출시"), "베스트셀러 제품 소개": ("베스트셀러",)}

# ── 측정 정의 값 대조 ────────────────────────────────────────────────────────

def prereg_constants() -> dict[str, Any]:
    text = (gg.HERE / "PREREG.md").read_text(encoding="utf-8")
    m = re.search(r"<!-- CONSTANTS (\{.*?\}) -->", text, re.S)
    if not m:
        raise SystemExit("PREREG.md 에 CONSTANTS 줄이 없습니다")
    return json.loads(m.group(1))


def check_constants() -> dict[str, Any]:
    want = prereg_constants()
    have = {"POPULARITY_MIN_REVIEWS": gd.POPULARITY_MIN_REVIEWS,
            "GENERATION_EXCLUDED_FIELDS": sorted(gd.GENERATION_EXCLUDED_FIELDS)}
    if have != {k: (sorted(v) if isinstance(v, list) else v) for k, v in want.items()}:
        raise SystemExit(f"측정 정의 값이 PREREG.md 와 다릅니다: 지금 {have} / 등록 {want}")
    return have


# ── 공통 텍스트 ──────────────────────────────────────────────────────────────

def squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def snapshot_text(snapshot: dict[str, Any], fields: tuple[str, ...] | None = None) -> str:
    info = generation_product_info(snapshot)
    if fields:
        info = {k: v for k, v in info.items() if k in fields}
    return json.dumps(info, ensure_ascii=False)


def message_text(m: dict[str, Any]) -> str:
    return f"{m.get('title', '')}\n{m.get('message', '')}"


# ── 정규식 지표 ──────────────────────────────────────────────────────────────

_DATE_RES = [
    re.compile(r"(20\d\d)\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})\s*일?"),
    re.compile(r"(20\d\d)\s*년\s*(\d{1,2})\s*월(?!\s*\d)"),
]


def _dates(text: str) -> set[tuple[int, int, int]]:
    out = set()
    for rx in _DATE_RES:
        for m in rx.finditer(text or ""):
            g = m.groups()
            out.add((int(g[0]), int(g[1]), int(g[2]) if len(g) > 2 and g[2] else 0))
    return out


def regex_metrics(m: dict[str, Any], brand_profile: str) -> dict[str, Any]:
    snap = m["product_snapshot"]
    full = snapshot_text(snap)
    full_sq = squash(full)
    evidence = squash(snapshot_text(snap, ("proof_points", "value", "summary", "product_comment", "key_benefits")))
    text = message_text(m)
    purpose = m.get("purpose", "")
    out: dict[str, Any] = {}

    # 날짜 — 상품정보(등록 시각 제외)에 없는 날짜, DB 등록 시각과 같은 날짜(점검 항목)
    snap_dates = _dates(full)
    snap_months = {(y, mo) for y, mo, _ in snap_dates}
    msg_dates = _dates(text)
    out["date_unsupported"] = sorted(
        f"{y}-{mo:02d}-{d:02d}" for y, mo, d in msg_dates
        if (y, mo, d) not in snap_dates and not (d == 0 and (y, mo) in snap_months))
    created = str(snap.get("product_created_at") or "")[:10]
    out["date_from_created_at"] = bool(created) and any(
        f"{y}-{mo:02d}-{d:02d}" == created for y, mo, d in msg_dates if d)

    # 시험 · 임상 언급 — 종류어(테스트 · 임상 · 시험 · 인체적용)가 근거 필드에 없거나, 앞말이 근거 필드에 없음
    stop = {"결과", "완료", "확인", "관련", "진행", "상세", "에서", "지금", "제품", "데이터", "자료", "보기", "근거"}
    tests = []
    for mt in re.finditer(r"([가-힣A-Za-z·\s]{0,14}?)(테스트|임상|시험|인체\s?적용)", text):
        kind = squash(mt.group(2))
        # 바로 앞 두 낱말만 수식어로 본다(멀리 있는 말은 다른 문맥일 수 있다)
        quals = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", mt.group(1)) if w not in stop][-2:]
        missing = [w for w in quals if squash(w) not in evidence]
        if kind not in evidence or missing:
            tests.append(squash(mt.group(0)))
    out["test_unsupported"] = tests

    # 판매인기 · 기간 — 경계 표(GROUNDING_DEF)를 따른다. 고른 목적의 라벨 단어는 뺀다
    has_sales = bool(re.search(r"누적|판매|1위|순위|랭킹|베스트", full))
    has_period = bool(re.search(r"누적|\d{4}\s*년\s*출시|년째|스테디", full))
    reviews = snap.get("review_count") or 0
    labels = LABEL_WORDS.get(purpose, ())
    pop = []
    # 페르소나 서술("선택하는 분") · 사용법("꾸준히 사용")은 걸리지 않게 인기 · 기간 결합형만 본다
    for mt in re.finditer(r"베스트셀러|스테디셀러|사랑받|선택받|많은\s?분(?:들)?이\s?선택|많은\s?사람(?:들)?이\s?선택|많이\s?찾|"
                          r"입소문|화제의|품절|\d+\s?년째|오랫동안\s?(?:사랑|선택)|꾸준히\s?(?:사랑|선택|찾)", text):
        word = mt.group(0)
        if word in labels:
            continue
        period = bool(re.search(r"스테디|년째|오랫동안|꾸준히|사랑받", word))
        ok = has_period if period else (has_sales or reviews >= gd.POPULARITY_MIN_REVIEWS)
        if not ok:
            pop.append(squash(word))
    out["popularity_unsupported"] = pop

    # 변화 · 차별 — 라벨(NEW · 신제품)은 대상 아님
    has_change = bool(re.search(r"리뉴얼|기존|업그레이드|NEW|New|새로워|강화된|개선된|업데이트", full))
    changes = [squash(x) for x in re.findall(r"달라진|달라졌|기존\s?(?:제품|대비|보다)|업그레이드|리뉴얼|새로워진|"
                                             r"더\s?강력해진|한층\s?업그레이드", text)]
    out["change_unsupported"] = [] if has_change else changes

    # 검증 주장
    proof = squash(snapshot_text(snap, ("proof_points", "value")))
    has_proof = bool(re.search(r"시험|임상|인증|수상|테스트|검증", proof))
    out["verified_unsupported"] = [] if has_proof else [squash(x) for x in re.findall(r"검증[가-힣]{0,3}", text)]

    # 브랜드 가이드 속 사실 표현 — 사실 표지가 있는 토막이 메시지에 들어갔고 상품정보에 없는 것
    marker = re.compile(r"\d|%|퍼센트|명\s?중|(?:하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|스무|서른)\s?(?:명|개|가지|배)|"
                        r"점유율|순위|1위|특허|수상|인증|검증|전문|미용실|최초")
    text_sq = squash(text)
    fact_tokens = set()
    for chunk in re.split(r"[,\n.·/]", brand_profile or ""):
        for tok in re.findall(r"[가-힣A-Za-z0-9%]+", chunk):
            if len(tok) >= 2 and marker.search(tok) and not re.fullmatch(r"\d+", tok):
                fact_tokens.add(tok)
    out["brand_fact_unsupported"] = sorted(t for t in fact_tokens if t in text_sq and t not in full_sq)
    kw = re.search(r"5\.\s*핵심 키워드\s*\n(.+)", brand_profile or "")
    slogans = [k.strip() for k in kw.group(1).split(",")] if kw else []
    out["slogan_used"] = sorted(k for k in slogans if k and not marker.search(k) and squash(k) in text_sq)

    out["any_unsupported"] = any(out[k] for k in ("date_unsupported", "test_unsupported", "popularity_unsupported",
                                                  "change_unsupported", "verified_unsupported", "brand_fact_unsupported"))
    return out


# ── 형식 · CTA · 1단계 ───────────────────────────────────────────────────────

def format_metrics(m: dict[str, Any], detector: Any) -> dict[str, Any]:
    title, body = m.get("title", ""), m.get("message", "")
    sents = review_kit.split_sentences(body)
    return {
        "json_ok": bool(m.get("json_ok", bool(title))),
        "title_len": len(title), "body_len": len(body),
        "title_over": len(title) > TITLE_MAX, "body_over": len(body) > BODY_MAX,
        "cta_last": bool(sents) and is_cta(sents[-1]),
        "stage1_hits": detector._detect_forbidden_expressions(f"{title} {body}"),
    }


# ── 판정기 (run_gate.judge 본문 복사) ─────────────────────────────────────────

async def judge(checker: Any, m: dict[str, Any], run: int, sem: asyncio.Semaphore) -> dict[str, Any]:
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier, reasoning_effort="low")
    snap = m["product_snapshot"]
    async with sem:
        attempts, latencies = 0, []
        scores: dict[str, Any] | None = None
        passed = False
        while attempts < 2:
            attempts += 1
            t0 = time.perf_counter()
            passed, scores = await checker._run_llm_judge(
                m.get("title", ""), m.get("message", ""), snap.get("product_name", ""), snap, m["purpose"],
                m["brand"], llm, persona_info=m["persona_info"],
            )
            latencies.append(round(time.perf_counter() - t0, 2))
            if scores and "accuracy" in scores:
                break
    missing = not (scores and "accuracy" in scores)
    return {"run": run, "missing": missing, "passed": None if missing else passed,
            "scores": None if missing else {k: scores[k] for k in (*SCORE_KEYS, "overall")},
            "attempts": attempts, "latency_s": latencies}


# ── LLM 근거 검증 ────────────────────────────────────────────────────────────

CLAIM = {
    "type": "object", "additionalProperties": False,
    "required": ["span", "type", "db_judgment", "source", "closest_db_text", "reason"],
    "properties": {
        "span": {"type": "string"},
        "type": {"type": "string", "enum": list(gd.CLAIM_TYPES)},
        "db_judgment": {"type": "string", "enum": ["없음", "다름"]},
        "source": {"type": "string", "enum": list(gd.SOURCES)},
        "closest_db_text": {"type": "string"},
        "reason": {"type": "string"},
    },
}
SUPPORTED = {
    "type": "object", "additionalProperties": False, "required": ["span", "type", "db_field"],
    "properties": {"span": {"type": "string"}, "type": {"type": "string", "enum": list(gd.CLAIM_TYPES)},
                   "db_field": {"type": "string"}},
}
VERIFIER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["unsupported_claims", "supported_claims", "purpose_conveyed"],
    "properties": {
        "unsupported_claims": {"type": "array", "items": CLAIM},
        "supported_claims": {"type": "array", "items": SUPPORTED},
        "purpose_conveyed": {"type": "object", "additionalProperties": False, "required": ["value", "reason"],
                             "properties": {"value": {"type": "string", "enum": ["O", "X"]},
                                            "reason": {"type": "string"}}},
    },
}

VERIFIER_SYSTEM = """당신은 화장품 · 뷰티 CRM 메시지의 사실 근거를 검증하는 검수자입니다.
메시지 속 '상품 사실 주장'이 이 상품의 상품정보에 근거가 있는지 판단합니다.

정의 (사람 검수자와 같은 문장)
{definition}

작업
1. 메시지에서 정의의 8가지 유형에 해당하는 상품 사실 주장을 모두 찾습니다. 정의에서 '대상이 아닌 것'은 찾지 않습니다.
2. 주장마다 상품정보와 대조합니다. 상품정보의 모든 필드를 끝까지 확인한 뒤 판단합니다.
   특성어긋남은 상품정보와 어긋날 때만 근거 없음이고, 상품정보에 없을 뿐인 일반 묘사는 아예 주장으로 올리지 않습니다.
   - 근거가 있으면 supported_claims 에 넣고, 근거가 된 필드 이름을 db_field 에 적습니다.
   - 근거가 없거나 내용이 다르면 unsupported_claims 에 넣습니다. db_judgment 는 '없음'(상품정보에 해당 내용이 없음)
     또는 '다름'(상품정보와 내용이 어긋남)입니다. source 는 근거가 브랜드 프로필에만 있으면 '브랜드 프로필에만 있음',
     아니면 'DB·프로필 모두 없음'입니다. closest_db_text 에는 상품정보에서 가장 가까운 문구를 그대로 옮기고, 없으면
     빈 문자열로 둡니다.
3. span 은 메시지의 해당 구간을 한 글자도 바꾸지 말고 그대로 옮깁니다(근거 없는 부분만 짧게).
4. purpose_conveyed: 메시지가 고른 발송 목적을 고객에게 전달하는지 O/X 로 답합니다.
reason 은 한국어 한 문장입니다."""


def verifier_user(m: dict[str, Any], brand_profile: str) -> str:
    info = generation_product_info(m["product_snapshot"])
    return "\n\n".join([
        f"[발송 목적] {m['purpose']}",
        "[페르소나]\n" + str(m.get("persona_info", {}).get("페르소나 정보", "")),
        "[상품정보]\n" + json.dumps(info, ensure_ascii=False, indent=1),
        "[브랜드 프로필 — LLM 이 만든 브랜드 톤 문서]\n" + (brand_profile or "(없음)"),
        f"[메시지 제목]\n{m.get('title', '')}",
        f"[메시지 본문]\n{m.get('message', '')}",
    ])


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


def postprocess(m: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    text_sq = squash(message_text(m))
    snap = snapshot_text(m["product_snapshot"])
    snap_sq, snap_nums = squash(snap), _numbers(snap)
    claims = []
    # 정의상 특성어긋남은 상품정보와 '어긋날 때'만 센다 — DB 판정이 '없음'인 특성 주장은 정의 밖으로 빼고 수만 기록한다
    outside = [c for c in out["unsupported_claims"] if c["type"] == "특성어긋남" and c["db_judgment"] == "없음"]
    for c in out["unsupported_claims"]:
        if c in outside:
            continue
        in_msg = bool(squash(c["span"])) and squash(c["span"]) in text_sq
        nums = _numbers(c["span"])
        nouns = {n for n in bo._nouns(c["span"]) if len(n) >= 2}
        noun_ratio = (sum(1 for n in nouns if squash(n) in snap_sq) / len(nouns)) if nouns else 0.0
        auto = (c["db_judgment"] == "없음" and nums <= snap_nums
                and bool(nouns) and noun_ratio >= AUTO_REVIEW_NOUN_RATIO)
        claims.append({**c, "span_in_message": in_msg, "auto_review": auto, "noun_ratio": round(noun_ratio, 2)})
    valid = [c for c in claims if c["span_in_message"]]
    if any(not c["auto_review"] for c in valid):
        klass = "양성"
    elif valid:
        klass = "재검토"
    else:
        klass = "음성"
    return {"claims": claims, "supported_claims": out["supported_claims"], "class": klass,
            "llm_positive": klass in ("양성", "재검토"),
            "n_supported": len(out["supported_claims"]),
            "invalid_spans": sum(1 for c in claims if not c["span_in_message"]),
            "outside_definition": [c["span"] for c in outside],
            "purpose_conveyed": out["purpose_conveyed"]["value"],
            "purpose_reason": out["purpose_conveyed"]["reason"]}


# ── 실행 ─────────────────────────────────────────────────────────────────────

def load_messages(path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(path)
    bad = [r.get("item_id") for r in rows if "product_snapshot" not in r or "purpose" not in r]
    if bad:
        raise SystemExit(f"메시지 파일에 상품정보 · 목적이 없는 항목: {bad[:5]}")
    return rows


async def run(messages: list[dict[str, Any]], out_dir: Path, judge_runs: int, skip_verifier: bool) -> None:
    constants = check_constants()
    out_dir.mkdir(parents=True, exist_ok=True)
    tones = get_brand_tones().get("brand_ton_prompt", {})
    detector = run_d1.make_detector()

    # LLM 근거 검증 — 이미 한 항목은 건너뛴다(비용)
    vpath = out_dir / "verifier_raw.jsonl"
    done_v = {r["item_id"]: r for r in load_jsonl(vpath) if "output" in r} if vpath.exists() else {}
    system = VERIFIER_SYSTEM.format(definition=gd.definition_text())
    if not skip_verifier:
        client = llm_review.openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
        sem = asyncio.Semaphore(VERIFIER_CONCURRENCY)

        async def verify(m: dict[str, Any]) -> None:
            async with sem:
                res = await llm_review.call(client, system, verifier_user(m, str(tones.get(m["brand"], "") or "")),
                                            VERIFIER_SCHEMA, "grounding_verifier")
            rec = {"item_id": m["item_id"], "at": datetime.now(timezone.utc).isoformat(),
                   "system_sha": llm_review.sha(system), **res}
            with open(vpath, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if "output" in rec:
                done_v[m["item_id"]] = rec
            print(f"  검증 {m['item_id']} {'오류' if 'error' in rec else '완료'}")

        todo = [m for m in messages if m["item_id"] not in done_v]
        print(f"LLM 근거 검증 {len(todo)}건 (모델 {llm_review.MODEL}, 이미 한 {len(done_v)}건 건너뜀)")
        await asyncio.gather(*(verify(m) for m in todo))

    # 판정기 — 이미 한 (항목, 회차)는 건너뛴다
    jpath = out_dir / "judge_raw.jsonl"
    done_j: dict[tuple[str, int], dict[str, Any]] = {}
    if jpath.exists():
        for r in load_jsonl(jpath):
            if not r.get("missing"):
                done_j[(r["item_id"], r["run"])] = r
    if judge_runs:
        jsem = asyncio.Semaphore(JUDGE_CONCURRENCY)

        async def one_judge(m: dict[str, Any], run_no: int) -> None:
            res = await judge(detector, m, run_no, jsem)
            rec = {"item_id": m["item_id"], **res}
            with open(jpath, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if not rec["missing"]:
                done_j[(m["item_id"], run_no)] = rec

        jobs = [(m, k) for m in messages for k in range(1, judge_runs + 1) if (m["item_id"], k) not in done_j]
        print(f"판정기 {len(jobs)}회 (low, 회차 {judge_runs})")
        await asyncio.gather(*(one_judge(m, k) for m, k in jobs))

    rows = []
    for m in messages:
        profile = str(tones.get(m["brand"], "") or "")
        v = done_v.get(m["item_id"])
        runs = [done_j[(m["item_id"], k)] for k in range(1, judge_runs + 1) if (m["item_id"], k) in done_j]
        rows.append({
            "item_id": m["item_id"], "purpose": m["purpose"],
            "regex": regex_metrics(m, profile),
            "format": format_metrics(m, detector),
            "verifier": postprocess(m, v["output"]) if v else None,
            "judge": runs,
        })
    write_jsonl(out_dir / "measure.jsonl", rows)
    meta = {
        "measured_at": datetime.now(timezone.utc).isoformat(), "n": len(rows),
        "verifier_model": llm_review.MODEL, "verifier_effort": llm_review.REASONING_EFFORT,
        "verifier_system_sha": llm_review.sha(system), "judge_runs": judge_runs,
        "judge_model": settings.chatgpt_model_name,
        "constants": constants, "prereg": gg.prereg_status() if gg.BASELINE.exists() else "잠금 전",
        "gate_files": gg.file_hashes(gg.GATE_FILES),
        "verifier_missing": [m["item_id"] for m in messages if m["item_id"] not in done_v] if not skip_verifier else "생략",
    }
    (out_dir / "measure_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    pos = sum(1 for r in rows if r["verifier"] and r["verifier"]["llm_positive"])
    print(f"→ {out_dir / 'measure.jsonl'}  n={len(rows)} · LLM 양성(재검토 포함) {pos} · 정규식 양성 "
          f"{sum(r['regex']['any_unsupported'] for r in rows)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=gg.SETS)
    parser.add_argument("--tag", choices=("before", "after"))
    parser.add_argument("--messages", default=None, help="메시지 파일을 직접 줄 때(잠금 전 시험)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--judge-runs", type=int, default=0)
    parser.add_argument("--skip-verifier", action="store_true")
    args = parser.parse_args()
    if args.messages:
        path, out = Path(args.messages), Path(args.out or Path(args.messages).parent)
    else:
        if not (args.set and args.tag):
            raise SystemExit("--set 과 --tag, 또는 --messages 를 준다")
        out = gg.set_dir(args.set) / args.tag
        path = out / "messages.jsonl"
    asyncio.run(run(load_messages(path), out, args.judge_runs, args.skip_verifier))


if __name__ == "__main__":
    main()
