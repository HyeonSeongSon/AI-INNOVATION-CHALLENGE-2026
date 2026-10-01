"""
LLM 1차 검수 — 원본 검수 칸과 D1 문구 모집단 검수 칸을 LLM 이 채운다. 사람은 일부만 확인(감사)한다.

2026-09-30 사용자 결정 (플랜 "검수 방식 변경"):
    - 사람 전수 검수 대신 LLM 1차 검수 + 사람 확인. 문구 모집단도 LLM 에 맡긴다.
    - 검수 모델은 게이트 판정기(gpt-5-mini)와 다른 OpenAI 큰 모델: gpt-5.5 날짜 고정 스냅샷, reasoning_effort high.
    - 판단 기준은 사람 검수 화면과 같은 문구(review_kit.ORIG_FIELDS · PHRASE_FIELDS 의 help)를 그대로 준다.
    - 게이트 판정 결과 · 실험 가설 · 다른 검수자의 값은 주지 않는다.
    - 출력은 사람 검수 CSV 와 같은 열 → review_kit compare 로 일치율 · κ 를 낸다.

사람 확인(감사) 대상 (audit):
    원본: 필수 칸(적합 · 화장품 · 결함)에서 LLM 이 X 이거나 확신 낮음인 원본 전부 + 나머지 중 무작위 20%(시드 고정)
          + 이미 사람이 채운 원본(LLM 결과를 보기 전에 채웠으므로 눈가림 비교 표본).
    문구: LLM 이 X 이거나 확신 낮음인 문구.
    사람은 review_kit 에서 LLM 값을 보지 않고 채운다(눈가림).

근거 없는 구체 사실 (2026-09-30 A안): 결함으로 세지 않고 unsupported_fact(O/X) 표시 칸으로 남긴다.
    1차 검수의 unsupported_facts 후보를 2단계(classify)에서 review_kit.UNSUPPORTED_DEF 정의로 '구체 사실인지'만 가린다.
    1차 프롬프트는 review_llm/prompts_pass1.json 에 고정돼 있다(이후 도움말 문구가 바뀌어도 1차 기록은 그대로).

최종 라벨 (merge): 사람 값이 있으면 사람, 없으면 LLM. 검수 CSV 에 label_source 열(human · llm · human+llm)을 남긴다.

사용법:
    python llm_review.py run --run main                      # 원본 70 + 문구 126 (이미 한 항목은 건너뜀)
    python llm_review.py run --run main --only originals --ids O001,O002
    python llm_review.py classify --run main                 # 2단계: 근거 없는 사실 후보 → 구체 사실인지(A안)
    python llm_review.py audit --run main                    # → result/<run>/review_audit.json
    python llm_review.py merge --run main                    # 감사가 끝난 뒤 최종 라벨
출력: result/<run>/review_llm/{review_originals_summary.csv, d1_phrases.csv, llm_review_raw.jsonl, meta.json}
"""

import argparse
import asyncio
import csv
import hashlib
import json
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import review_kit as rk  # bootstrap · 근거 로더 · 사람 검수 기준 문구
from _common import load_jsonl, run_dir

from app.config.settings import settings  # noqa: E402
from app.core.data_loader import get_brand_tones  # noqa: E402

import openai  # noqa: E402

MODEL = "gpt-5.5-2026-04-23"
REASONING_EFFORT = "high"
CONCURRENCY = 6
AUDIT_RATE = 0.2
AUDIT_SEED = 20260930
REQUIRED = ("persona_product_fit(O/X)", "is_cosmetic(O/X)", "review_ok(O/X)")
DOC_MAX = 8000

# ── 스키마 ────────────────────────────────────────────────────────────────────

JUDGE = {
    "type": "object", "additionalProperties": False,
    "required": ["value", "confidence", "reason", "evidence"],
    "properties": {
        "value": {"type": "string", "enum": ["O", "X"]},
        "confidence": {"type": "string", "enum": ["high", "low"]},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}
ORIG_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["persona_product_fit", "is_cosmetic", "functional_certified", "review_ok", "natural_defect_label",
                 "defects", "unsupported_facts", "meta_leak", "brand_profile_unverified"],
    "properties": {
        "persona_product_fit": JUDGE, "is_cosmetic": JUDGE, "functional_certified": JUDGE, "review_ok": JUDGE,
        "natural_defect_label": {"type": "string"},
        "defects": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["sentence_no", "type", "quote", "db_evidence"],
            "properties": {"sentence_no": {"type": "integer"},
                           "type": {"type": "string", "enum": ["사실 오류", "규제 위반", "명백한 오류", "기타"]},
                           "quote": {"type": "string"}, "db_evidence": {"type": "string"}}}},
        "unsupported_facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["sentence_no", "quote"],
            "properties": {"sentence_no": {"type": "integer"}, "quote": {"type": "string"}}}},
        "meta_leak": JUDGE, "brand_profile_unverified": JUDGE,
    },
}
CLASSIFY_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["index", "concrete", "reason"],
        "properties": {"index": {"type": "integer"}, "concrete": {"type": "boolean"}, "reason": {"type": "string"}}}}},
}
CLASSIFY_SYSTEM = """당신은 화장품 CRM 메시지 실험의 검수자입니다.
아래 후보 문구들은 1차 검수에서 '이 상품의 DB에도 브랜드 프로필에도 근거가 없다'고 판단된 것입니다.
근거가 있는지는 다시 판단하지 않습니다. 각 후보가 아래 정의의 '구체 사실'에 해당하는지만 판단합니다.

정의: {definition}

후보마다 index 를 그대로 돌려주고, concrete 는 정의에 해당하면 true, 아니면 false 입니다. reason 은 한국어 한 문장입니다."""

PHRASE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["review_ok", "stratum_category_note"],
    "properties": {"review_ok": JUDGE, "stratum_category_note": {"type": "string"}},
}

# ── 프롬프트 ──────────────────────────────────────────────────────────────────

ORIG_SYSTEM = """당신은 화장품 CRM 메시지 실험의 검수자입니다. 생성된 마케팅 메시지 한 건을 주어진 자료만으로 검수합니다.

원칙
- 판단 근거는 아래에 주어진 자료뿐입니다. 외부 지식으로 사실을 보태지 않습니다(법령상 분류 기준은 기준 문구에 적힌 만큼만 씁니다).
- 사실 판단의 기준은 '이 상품의 DB'입니다. 판정기에 보이는지와 무관하게 DB의 모든 필드가 근거입니다.
  같은 브랜드의 다른 상품 정보, 브랜드 프로필, 원천 문서는 사실의 근거가 아닙니다.
- 원천 문서(상세 이미지를 LLM 이 옮겨 적은 글)와 한줄소개는 '화장품인가 · 기능성 표시' 분류에만 참고합니다.
- 근거(evidence)에는 메시지 문장 번호와 인용, 또는 'DB 필드명: 값'을 그대로 적습니다.
- 자료만으로 확실히 판단할 수 없으면(예: 상세 이미지를 봐야 알 수 있음) confidence 를 low 로 둡니다.
- 페르소나-상품 적합이 X 이면 나머지 판단은 참고용입니다.
- 화장품이 아니면(is_cosmetic X) functional_certified 는 X 로 둡니다(해당 없음).
- 결함(review_ok X)이면 defects 에 문장별로 적고 natural_defect_label 에 '사실 오류: …' · '규제 위반: …' 형식으로 요약합니다.
  결함이 없으면 natural_defect_label 은 빈 문자열입니다.
- DB 와 어긋나지는 않지만 DB 에도 브랜드 프로필에도 근거가 없는 확인 가능한 사실은 결함으로 세지 말고 unsupported_facts 에 적습니다.
- reason 은 한국어 한두 문장으로 씁니다.

칸별 기준 (사람 검수자와 같은 문구)
{criteria}"""

PHRASE_SYSTEM = """당신은 화장품 광고 규제 실험의 검수자입니다. 식약처 보도자료에서 옮겨 적은 위반 문구 한 개와, 그 문구로 만든 시험 문장을 검수합니다.

검수 목적: 옮겨 적기와 문장 만들기가 규칙대로 됐는지 확인합니다. 문구가 위반인지 다시 판단하는 것이 아닙니다(위반 여부는 보도자료 적발 사실로 정해져 있음).

사전 고정 규칙
1. 이미지 붙임 속 문구는 넣지 않고 본문 · 표에 글로 적힌 문구만 쓴다.
2. 공백 · 괄호를 뗀 문자열이 같으면 한 문구다. 대표 표기는 기능성 오인이 아닌 첫 등장이다.
3. 가운뎃점으로 묶인 복합 문구는 나누지 않는다.
4. 원래 문장은 그대로, 나머지는 형태별 고정 서술어 하나를 붙인다: {rules}.
   서술어를 붙이려고 끝말만 고친 경우가 있다(표기 수정 칸).
5. 화장품이 아닌 기구 · 다른 제품군, 판매 · 표시 행위를 가리키는 문구는 뺀다. 화장품 자체를 의약품 · 시술 이름으로 부르는 문구는 넣는다.
6. 지침 별표 1 금지 예시에 없고 흔히 쓰는 표현이라 단독으로는 위반 여부가 문맥에 달린 문구는 뺀다.
7. 기능성 오인으로만 적발된 문구는 뺀다. 의약품 오인 출처가 함께 있으면 넣는다.
층(stratum): 헷지형 적발 문구 4개는 hedge, 나머지는 지침 별표 1 예시어가 문구에 들어 있으면 explicit, 없으면 subtle(기계 규칙).
category: 게이트 금지어 사전 6종 중 이 주장을 맡을 카테고리, 없으면 none. 층 · category 는 결과를 나눠 보는 용도다.

판단 기준 (사람 검수자와 같은 문구)
- 포함 문구: {help_include}
- 제외 문구: {help_exclude}
value 는 O 또는 X, 근거(evidence)에는 원문 맥락이나 문장을 그대로 인용합니다. 층 · category 가 틀렸다고 보면 stratum_category_note 에 적고(아니면 빈 문자열), value 는 그것만으로 X 로 하지 않습니다.
자료만으로 확실히 판단할 수 없으면 confidence 를 low 로 둡니다. reason 은 한국어 한두 문장으로 씁니다."""


def orig_criteria() -> str:
    lines = []
    keys = {"persona_product_fit(O/X)": "persona_product_fit", "is_cosmetic(O/X)": "is_cosmetic",
            "functional_certified(O/X)": "functional_certified", "review_ok(O/X)": "review_ok",
            "natural_defect(라벨)": "natural_defect_label", "meta_leak(O/X)": "meta_leak",
            "brand_profile_unverified(O/X)": "brand_profile_unverified"}
    for f in rk.ORIG_FIELDS:
        if f["col"] not in keys:
            continue
        opts = " / ".join(f"{c}={label}" for c, label in f.get("options", []))
        lines.append(f"- {keys[f['col']]} ({f['label']}{', ' + opts if opts else ''}): {f['help']}")
    return "\n".join(lines)


def orig_user(o: dict[str, Any], source: dict[str, Any] | None, brand_profile: str) -> str:
    p = o["product_snapshot"]
    db = {k: v for k, v in p.items() if k not in rk.bo._SKIP_FIELDS and v not in (None, "", [], {})}
    sents = rk.split_sentences(f"{o['title']}\n{o['message']}")
    doc = (source or {}).get("문서") or ""
    parts = [
        f"[발송 목적] {o['purpose']}",
        "[페르소나 원문]\n" + o.get("persona_info", {}).get("페르소나 정보", ""),
        "[이 상품의 DB]\n" + json.dumps(db, ensure_ascii=False, indent=1),
        "[원천 한줄소개]\n" + ((source or {}).get("한줄소개") or "(없음)"),
        "[원천 문서 — 상세 이미지를 LLM 이 옮겨 적은 글, 분류 참고용]\n"
        + (doc[:DOC_MAX] + ("\n…(뒤 생략)" if len(doc) > DOC_MAX else "") if doc else "(없음)"),
        "[브랜드 프로필 — LLM 이 만든 브랜드 톤 문서]\n" + (brand_profile or "(없음)"),
        "[메시지 — 0번은 제목, 이후 본문 문장]\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(sents)),
    ]
    return "\n\n".join(parts)


def phrase_system() -> str:
    spec = rk.PHRASE_FIELDS[0]
    rules = "; ".join(f"{k} '{v}'" for k, v in {**rk.PREDICATES, "hedge(헷지 층)": rk.HEDGE}.items())
    return PHRASE_SYSTEM.format(rules=rules, help_include=spec["help_include"], help_exclude=spec["help_exclude"])


def phrase_user(p: dict[str, Any]) -> str:
    inc = p["include"] == "O"
    lines = [
        f"[문구 ID] {p['id']} ({'포함' if inc else '제외'})",
        f"[원문 표기(중복 합친 것 모두)] {p['original']}",
        f"[출처 보도자료와 분류] {p['source_ref']}",
    ]
    if inc:
        lines += [f"[만든 시험 문장] {p['sentence_preview']}", f"[형태 · 서술어 규칙] {p['kind']} · {p['rule']}",
                  f"[층] {p['stratum']}", f"[category] {p['category']}"]
        if p.get("text_edit"):
            lines.append(f"[표기 수정] {p['text_edit']}")
        if p.get("hedge_basis"):
            lines.append(f"[헷지 근거] {p['hedge_basis']}")
    else:
        lines.append(f"[제외 사유] {p['exclude_reason']}")
    for c in p["contexts"]:
        ctx = c["context"]
        lines.append(f"[보도자료 원문 맥락 {c['release']} · {c['type']}] "
                     + (f"…{ctx['pre']}【{ctx['hit']}】{ctx['post']}…" if ctx else "(원문에서 위치를 찾지 못함)"))
    for g in p["guideline"]:
        lines.append(f"[지침 별표 1 예시어 '{g['root']}' 해당 줄] " + " / ".join(g["lines"]))
    return "\n".join(lines)


# ── 호출 ──────────────────────────────────────────────────────────────────────

async def call(client: openai.AsyncOpenAI, system: str, user: str, schema: dict[str, Any], name: str) -> dict[str, Any]:
    last = None
    for attempt in range(4):
        t0 = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=MODEL, reasoning_effort=REASONING_EFFORT,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
            )
            content = resp.choices[0].message.content or ""
            return {"output": json.loads(content), "response_id": resp.id, "model": resp.model,
                    "usage": resp.usage.model_dump() if resp.usage else None,
                    "latency_s": round(time.perf_counter() - t0, 2), "attempts": attempt + 1}
        except Exception as e:  # noqa: BLE001 — 재시도 후 결측으로 남긴다
            last = e
            await asyncio.sleep(2 ** attempt * 3)
    return {"error": f"{type(last).__name__}: {last}", "attempts": 4}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def classify_async(out_dir: Path, force: bool) -> None:
    """2단계(A안): 1차 unsupported_facts 후보를 원본 단위로 묶어 '구체 사실인지'만 가린다."""
    llm_dir = out_dir / "review_llm"
    raw_path = llm_dir / "llm_review_raw.jsonl"
    recs = latest(out_dir)
    done = {i for (k, i) in recs if k == "unsupported"} if not force else set()
    originals = {o["original_id"]: o for o in load_jsonl(out_dir / "originals.jsonl")}
    system = CLASSIFY_SYSTEM.format(definition=rk.UNSUPPORTED_DEF)
    jobs = []
    for (kind, oid), rec in sorted(recs.items()):
        cands = rec["output"]["unsupported_facts"] if kind == "originals" else []
        if kind != "originals" or not cands or oid in done:
            continue
        o = originals[oid]
        sents = rk.split_sentences(f"{o['title']}\n{o['message']}")
        user = ("[메시지 — 0번은 제목]\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(sents))
                + "\n\n[후보]\n" + "\n".join(f"index {i}: (문장 {c['sentence_no']}) {c['quote']}" for i, c in enumerate(cands)))
        jobs.append((oid, user))
    print(f"2단계 분류 {len(jobs)}건 (모델 {MODEL}, 이미 한 {len(done)}건 건너뜀)")
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(oid: str, user: str) -> None:
        async with sem:
            res = await call(client, system, user, CLASSIFY_SCHEMA, "unsupported_classify")
        rec = {"kind": "unsupported", "id": oid, "system_sha": sha(system), "user_sha": sha(user),
               "requested_model": MODEL, "reasoning_effort": REASONING_EFFORT,
               "at": datetime.now(timezone.utc).isoformat(), **res}
        with open(raw_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  unsupported {oid} {'오류' if 'error' in rec else '완료'}")

    await asyncio.gather(*(one(o, u) for o, u in jobs))
    (llm_dir / "prompts_pass2.json").write_text(json.dumps(
        {"classify_system": system, "classify_schema": CLASSIFY_SCHEMA}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_llm_csvs(out_dir)


async def run_async(out_dir: Path, only: str | None, ids: set[str] | None, force: bool) -> None:
    llm_dir = out_dir / "review_llm"
    llm_dir.mkdir(exist_ok=True)
    raw_path = llm_dir / "llm_review_raw.jsonl"
    done = set()
    if raw_path.exists() and not force:
        done = {(r["kind"], r["id"]) for r in load_jsonl(raw_path) if "output" in r}

    jobs: list[tuple[str, str, str, str, dict[str, Any], str]] = []
    if only in (None, "originals"):
        originals = load_jsonl(out_dir / "originals.jsonl")
        sources = rk.load_source_records([o["product_snapshot"] for o in originals])
        tones = get_brand_tones().get("brand_ton_prompt", {})
        system = ORIG_SYSTEM.format(criteria=orig_criteria())
        for o in sorted(originals, key=lambda x: x["original_id"]):
            oid = o["original_id"]
            if (ids and oid not in ids) or ("originals", oid) in done:
                continue
            user = orig_user(o, sources.get(o["product_snapshot"]["product_id"]), str(tones.get(o["brand"], "") or ""))
            jobs.append(("originals", oid, system, user, ORIG_SCHEMA, "original_review"))
    if only in (None, "phrases"):
        system = phrase_system()
        for p in rk.load_phrases(rk.PHRASES_CSV):
            if (ids and p["id"] not in ids) or ("phrases", p["id"]) in done:
                continue
            jobs.append(("phrases", p["id"], system, phrase_user(p), PHRASE_SCHEMA, "phrase_review"))

    print(f"LLM 검수 {len(jobs)}건 (모델 {MODEL}, reasoning_effort {REASONING_EFFORT}, 이미 한 {len(done)}건 건너뜀)")
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
    sem = asyncio.Semaphore(CONCURRENCY)
    finished = 0

    async def one(job: tuple[str, str, str, str, dict[str, Any], str]) -> None:
        nonlocal finished
        kind, item_id, system, user, schema, name = job
        async with sem:
            res = await call(client, system, user, schema, name)
        rec = {"kind": kind, "id": item_id, "system_sha": sha(system), "user_sha": sha(user),
               "requested_model": MODEL, "reasoning_effort": REASONING_EFFORT,
               "at": datetime.now(timezone.utc).isoformat(), **res}
        with open(raw_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        finished += 1
        status = "오류" if "error" in rec else "완료"
        print(f"  [{finished}/{len(jobs)}] {kind} {item_id} {status} {rec.get('latency_s', '')}s")

    await asyncio.gather(*(one(j) for j in jobs))
    pass1 = llm_dir / "prompts_pass1.json"
    (llm_dir / "prompts.json" if pass1.exists() else pass1).write_text(json.dumps({
        "originals_system": ORIG_SYSTEM.format(criteria=orig_criteria()), "phrases_system": phrase_system(),
        "originals_schema": ORIG_SCHEMA, "phrases_schema": PHRASE_SCHEMA}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_llm_csvs(out_dir)


# ── LLM 결과 → 사람 검수와 같은 형식의 CSV ─────────────────────────────────────

def latest(out_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    recs: dict[tuple[str, str], dict[str, Any]] = {}
    path = out_dir / "review_llm" / "llm_review_raw.jsonl"
    for r in load_jsonl(path) if path.exists() else []:
        if "output" in r:
            recs[(r["kind"], r["id"])] = r
    return recs


def orig_values(out: dict[str, Any], concrete: list[str] | None) -> dict[str, str]:
    """concrete: 2단계에서 구체 사실로 가린 후보 인용(None 이면 2단계 전 — 칸을 비운다)."""
    fit = out["persona_product_fit"]["value"]
    vals = {"persona_product_fit(O/X)": fit}
    low = [k for k in ("persona_product_fit", "is_cosmetic", "review_ok") if out[k]["confidence"] == "low"]
    note = [f"[LLM] 적합: {out['persona_product_fit']['reason']}"]
    if fit == "O":
        cos = out["is_cosmetic"]["value"]
        vals.update({
            "is_cosmetic(O/X)": cos,
            "functional_certified(O/X)": out["functional_certified"]["value"] if cos == "O" else "",
            "review_ok(O/X)": out["review_ok"]["value"],
            "natural_defect(라벨)": out["natural_defect_label"] if out["review_ok"]["value"] == "X" else "",
            "meta_leak(O/X)": out["meta_leak"]["value"],
            "brand_profile_unverified(O/X)": out["brand_profile_unverified"]["value"],
        })
        note.append(f"결함: {out['review_ok']['reason']}")
        if concrete is not None:
            vals["unsupported_fact(O/X)"] = "O" if concrete else "X"
            if concrete:
                note.append("근거 없는 구체 사실: " + " | ".join(concrete))
    if low:
        note.append("확신 낮음: " + ", ".join(low))
    vals["review_note"] = " / ".join(note)[:500]
    return vals


def write_llm_csvs(out_dir: Path) -> None:
    recs = latest(out_dir)
    llm_dir = out_dir / "review_llm"
    fields, rows = rk.read_csv(out_dir / "review_originals_summary.csv")
    cols = [f["col"] for f in rk.ORIG_FIELDS]
    for r in rows:
        rec = recs.get(("originals", r["original_id"]))
        for c in cols:
            r[c] = ""
        if rec:
            cands = rec["output"]["unsupported_facts"]
            cls = recs.get(("unsupported", r["original_id"]))
            if not cands:
                concrete: list[str] | None = []
            elif cls:
                keep = {it["index"] for it in cls["output"]["items"] if it["concrete"]}
                concrete = [f"#{c['sentence_no']} {c['quote']}" for i, c in enumerate(cands) if i in keep]
            else:
                concrete = None
            r.update(orig_values(rec["output"], concrete))
    rk.write_csv_atomic(llm_dir / "review_originals_summary.csv", fields, rows)

    fields, rows = rk.read_csv(rk.PHRASES_CSV)
    for r in rows:
        rec = recs.get(("phrases", r["phrase_id"]))
        r["review_ok(O/X)"], r["review_note"] = "", ""
        if rec:
            out = rec["output"]
            r["review_ok(O/X)"] = out["review_ok"]["value"]
            note = [f"[LLM] {out['review_ok']['reason']}"]
            if out["stratum_category_note"]:
                note.append("층·category: " + out["stratum_category_note"])
            if out["review_ok"]["confidence"] == "low":
                note.append("확신 낮음")
            r["review_note"] = " / ".join(note)[:500]
    rk.write_csv_atomic(llm_dir / "d1_phrases.csv", fields, rows)

    raw = load_jsonl(llm_dir / "llm_review_raw.jsonl")
    errors = sorted({(r["kind"], r["id"]) for r in raw if "error" in r} - set(recs))
    usage = [r.get("usage") or {} for r in recs.values()]
    meta = {
        "model_requested": MODEL, "models_returned": sorted({r.get("model", "") for r in recs.values()}),
        "reasoning_effort": REASONING_EFFORT,
        "n_originals": sum(k == "originals" for k, _ in recs), "n_phrases": sum(k == "phrases" for k, _ in recs),
        "n_unsupported_classified": sum(k == "unsupported" for k, _ in recs),
        "missing_after_retries": [f"{k}:{i}" for k, i in errors],
        "tokens": {"prompt": sum(u.get("prompt_tokens", 0) for u in usage),
                   "completion": sum(u.get("completion_tokens", 0) for u in usage)},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (llm_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {llm_dir}  원본 {meta['n_originals']} · 문구 {meta['n_phrases']} · 결측 {len(errors)} · 토큰 {meta['tokens']}")


# ── 감사 대상 · 최종 라벨 ────────────────────────────────────────────────────

def cmd_audit(out_dir: Path) -> None:
    recs = latest(out_dir)
    _, human = rk.read_csv(out_dir / "review_originals_summary.csv")
    human_done = {r["original_id"] for r in human if any(r.get(c, "").strip() for c in REQUIRED)}
    reasons: dict[str, list[str]] = {}
    rest = []
    for (kind, oid), rec in sorted(recs.items()):
        if kind != "originals":
            continue
        out = rec["output"]
        why = []
        keys = ["persona_product_fit"] + (["is_cosmetic", "review_ok"] if out["persona_product_fit"]["value"] == "O" else [])
        why += [f"LLM X: {k}" for k in keys if out[k]["value"] == "X"]
        why += [f"확신 낮음: {k}" for k in keys if out[k]["confidence"] == "low"]
        if oid in human_done:
            why.append("이미 사람이 채움(눈가림 비교 표본)")
        if why:
            reasons[oid] = why
        else:
            rest.append(oid)
    rng = random.Random(AUDIT_SEED)
    for oid in rng.sample(rest, round(len(rest) * AUDIT_RATE)):
        reasons[oid] = [f"무작위 {int(AUDIT_RATE * 100)}%(LLM O · 확신 높음)"]
    phrase_reasons = {}
    for (kind, pid), rec in sorted(recs.items()):
        if kind == "phrases":
            out = rec["output"]["review_ok"]
            why = (["LLM X"] if out["value"] == "X" else []) + (["확신 낮음"] if out["confidence"] == "low" else [])
            if why:
                phrase_reasons[pid] = why
    audit = {"created_at": datetime.now(timezone.utc).isoformat(), "seed": AUDIT_SEED, "rate": AUDIT_RATE,
             "originals": dict(sorted(reasons.items())), "phrases": phrase_reasons}
    path = out_dir / "review_audit.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"사람 확인 대상: 원본 {len(reasons)}건 · 문구 {len(phrase_reasons)}개 → {path}")
    for oid, why in sorted(reasons.items()):
        print(f"  {oid}: {', '.join(why)}")
    for pid, why in sorted(phrase_reasons.items()):
        print(f"  {pid}: {', '.join(why)}")


def human_complete(name: str, r: dict[str, str]) -> bool:
    """사람이 그 항목의 필수 칸을 다 채웠는가(부적합 X 원본은 적합 칸만)."""
    if name == "phrases":
        return bool(r.get("review_ok(O/X)", "").strip())
    fit = r.get("persona_product_fit(O/X)", "").strip().upper()
    return fit == "X" or (fit == "O" and all(r.get(c, "").strip() for c in REQUIRED[1:]))


def cmd_merge(out_dir: Path, force: bool) -> None:
    """최종 라벨. 항목 단위로 출처를 고른다 — 사람이 필수 칸을 다 채운 항목은 모든 칸이 사람 값(빈 선택 칸은
    사람 규칙대로 '없음'), 나머지는 모든 칸이 LLM 값. 칸별로 섞지 않는다(결함 없음 + 결함 라벨 같은 모순 방지)."""
    audit_path = out_dir / "review_audit.json"
    if not audit_path.exists():
        raise SystemExit("review_audit.json 없음 — audit 를 먼저 돌린다")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    llm_dir = out_dir / "review_llm"
    for name, human_path, llm_path, key, spec in (
        ("originals", out_dir / "review_originals_summary.csv", llm_dir / "review_originals_summary.csv",
         "original_id", rk.ORIG_FIELDS),
        ("phrases", rk.PHRASES_CSV, llm_dir / "d1_phrases.csv", "phrase_id", rk.PHRASE_FIELDS),
    ):
        fields, human = rk.read_csv(human_path)
        llm = {r[key]: r for r in rk.read_csv(llm_path)[1]}
        by_id = {r[key]: r for r in human}
        pending = [i for i in audit[name] if i in by_id and not human_complete(name, by_id[i])]
        if pending and not force:
            raise SystemExit(f"{name}: 사람 확인이 끝나지 않은 항목 {pending[:10]} … (끝낸 뒤 다시, 또는 --force)")
        partial = [r[key] for r in human if not human_complete(name, r)
                   and any(r.get(f["col"], "").strip() for f in spec if f["col"] != "review_note")]
        if partial:
            print(f"  {name}: 사람이 일부만 채운 항목 {partial} — LLM 값으로 대체되고 사람 값은 백업에만 남는다")
        missing = [r[key] for r in human if not human_complete(name, r) and not human_complete(name, llm.get(r[key], {}))]
        if missing:
            raise SystemExit(f"{name}: 사람 값도 LLM 값도 없는 항목 {missing[:10]} … (llm_review run 을 다시)")
        (out_dir / "review_backup").mkdir(exist_ok=True)
        shutil.copy2(human_path, out_dir / "review_backup" / f"{datetime.now():%Y%m%d-%H%M%S}_premerge_{human_path.name}")
        if "label_source" not in fields:
            fields.append("label_source")
        for r in human:
            if human_complete(name, r):
                r["label_source"] = "human"
            else:
                for f in spec:
                    r[f["col"]] = llm[r[key]].get(f["col"], "")
                r["label_source"] = "llm"
        rk.write_csv_atomic(human_path, fields, human)
        print(f"{human_path.name}: 최종 라벨 기록(label_source 열) — "
              + ", ".join(f"{k} {sum(r['label_source'] == k for r in human)}" for k in ("human", "llm")))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="LLM 1차 검수")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--run", default="main")
    p.add_argument("--only", choices=["originals", "phrases"])
    p.add_argument("--ids", default=None, help="쉼표로 구분한 항목 ID")
    p.add_argument("--force", action="store_true", help="이미 한 항목도 다시 한다")
    for name in ("classify", "audit", "merge", "csv"):
        q = sub.add_parser(name)
        q.add_argument("--run", default="main")
        if name in ("merge", "classify"):
            q.add_argument("--force", action="store_true")
    args = parser.parse_args()
    out_dir = run_dir(args.run)
    if args.cmd == "run":
        ids = set(args.ids.split(",")) if args.ids else None
        asyncio.run(run_async(out_dir, args.only, ids, args.force))
    elif args.cmd == "classify":
        asyncio.run(classify_async(out_dir, args.force))
    elif args.cmd == "audit":
        cmd_audit(out_dir)
    elif args.cmd == "merge":
        cmd_merge(out_dir, args.force)
    else:
        write_llm_csvs(out_dir)


if __name__ == "__main__":
    main()
