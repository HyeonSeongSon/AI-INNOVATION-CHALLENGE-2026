"""
v2 측정 (사전 등록 파일, baseline_v2.json 으로 잠근다).

v1 measure.py 를 고치지 않고, 같은 함수는 import 해서 쓴다(판정기 · 형식 · 텍스트 도구). 바뀐 것:
- LLM 근거 검증 v2: 정의 v2(9개 유형), 추론 강도를 인자로 받는다(잠금 전 시험에서 high · medium 비교).
  메시지 층은 세 가지로 낸다.
    class         — 9개 유형 전체
    class_primary — 주 지표 유형(특성어긋남 · 근거없는고민연결)만 → v2 주 지표 · 사람 확인 층
    class_v1types — v1 의 8개 유형만 → 1라운드 사람 판정과 비교할 때
- 정규식 v2
  - 시험 · 임상: 수식어 불용어에 사용법 · 성분 · 섭취법 등을 추가하고(v1 은 CTA "사용법과 임상 확인"을 잘못 잡았다),
    종류어(임상 · 인체적용 · 테스트 · 시험)가 상품정보에 없는 경우를 따로 센다.
  - 새 지표: 숫자 · 단위 변형(C), 리뷰 기반 '검증'(D), 근거 없는 변화 암시 제목(E), CTA 틀("사용법과 ○○ 확인").

사용법:
    python measure_v2.py --messages <messages.jsonl> --out <dir> --effort medium [--judge-runs 2] [--skip-verifier]
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

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

import measure as m1  # noqa: E402 — v1 측정(판정기 · 형식 · 텍스트 도구 재사용, 파일은 고치지 않음)
import llm_review  # noqa: E402
import run_d1  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.data_loader import get_brand_tones  # noqa: E402

import grounding_def_v2 as gd  # noqa: E402
from app.agents.generate_message_agent.prompts.product_fields import generation_product_info  # noqa: E402

VERIFIER_MODEL = llm_review.MODEL  # gpt-5.5 날짜 고정 스냅숏(v1 과 같음)
VERIFIER_CONCURRENCY = 6
TEST_KINDS = ("임상", "인체적용", "테스트", "시험")

squash, snapshot_text, message_text, _numbers = m1.squash, m1.snapshot_text, m1.message_text, m1._numbers


# ── 정규식 v2 ────────────────────────────────────────────────────────────────

def regex_metrics_v2(m: dict[str, Any], brand_profile: str) -> dict[str, Any]:
    out = m1.regex_metrics(m, brand_profile)  # v1 지표(날짜 · 판매인기 · 변화 · 검증 · 브랜드 사실)는 그대로 둔다
    snap = m["product_snapshot"]
    full = snapshot_text(snap)
    full_sq = squash(full)
    evidence = squash(snapshot_text(snap, ("proof_points", "value", "summary", "product_comment", "key_benefits")))
    title, body = m.get("title", ""), m.get("message", "")
    text = message_text(m)

    # 시험 · 임상 v2 — 수식어 불용어 확대 + 종류어 자체가 상품정보에 없는 경우를 따로 센다
    stop = {"결과", "완료", "확인", "관련", "진행", "상세", "에서", "지금", "제품", "데이터", "자료", "보기", "근거",
            "사용법", "사용법과", "성분", "성분과", "섭취법", "섭취법과", "사용", "방법", "정보", "정보와", "핵심", "주요",
            "수치", "수치와", "지표", "효과", "함께", "직접"}
    tests, kind_missing = [], []
    for mt in re.finditer(r"([가-힣A-Za-z·\s]{0,14}?)(테스트|임상|시험|인체\s?적용)", text):
        kind = squash(mt.group(2))
        quals = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", mt.group(1)) if w not in stop][-2:]
        if kind not in full_sq:
            kind_missing.append(squash(mt.group(0)))
        elif kind not in evidence or [w for w in quals if squash(w) not in evidence]:
            tests.append(squash(mt.group(0)))
    out["test_unsupported_v2"] = tests
    out["test_kind_missing"] = kind_missing  # H: 상품정보에 그 종류어가 없는 시험 · 임상 언급

    # C 숫자 · 단위 변형 — 메시지의 '숫자+단위'가 상품정보에도 페르소나에도 없는 것(날짜 · 가격 · 할인율은 v1 지표가 본다)
    persona = str(m.get("persona_info", {}).get("페르소나 정보", "") or m.get("persona_info", ""))
    units = r"(초|분|시간|일|주|개월|년|배|%|퍼센트|단계|가지|종|회|ml|mL|g|mg|PPM|ppm)"
    snap_units = {squash(x.group(0)) for x in re.finditer(r"\d[\d,.]*\s?" + units, full)}
    persona_units = {squash(x.group(0)) for x in re.finditer(r"\d[\d,.]*\s?" + units, persona)}
    if snap.get("discount_rate") not in (None, ""):
        snap_units.add(f"{snap['discount_rate']}%")  # 할인율은 숫자로만 저장돼 있다
    mutated = []
    for mt in re.finditer(r"(\d[\d,.]*)\s?" + units, text):
        tok = squash(mt.group(0))
        if re.fullmatch(r"20\d\d년", tok) or re.search(r"월\s?$", text[max(0, mt.start() - 2):mt.start()]):
            continue  # 연도 · 날짜의 '일'은 날짜 지표가 본다
        if tok not in snap_units and tok not in persona_units and tok.replace(",", "") not in {s.replace(",", "") for s in snap_units}:
            mutated.append(tok)
    out["number_mutation"] = sorted(set(mutated))

    # D 리뷰 기반 '검증' — 리뷰 · 평점 · 후기를 근거로 든 검증 표현
    out["review_verified"] = [squash(x.group(0)) for x in re.finditer(r"(리뷰|평점|후기|사용평)[^.!?\n]{0,20}검증", text)]

    # E 근거 없는 변화 암시 제목
    has_change = bool(re.search(r"리뉴얼|기존|업그레이드|새로워|강화된|개선된|업데이트", full))
    out["change_hook_title"] = [] if has_change else [squash(x) for x in re.findall(r"달라진|달라졌|달랐던|새로워진|바뀐", title)]

    # CTA 틀 — 마지막 문장이 "사용법과 ○○ 확인" 꼴인지(보조 지표, 정형화 정도)
    sents = m1.review_kit.split_sentences(body)
    out["cta_template_usage"] = bool(sents) and bool(re.search(r"사용법\s?(과|·|,|와)", sents[-1]))

    out["cleanup_any"] = any(out[k] for k in ("number_mutation", "review_verified", "change_hook_title", "test_kind_missing"))
    return out


# ── LLM 근거 검증 v2 ─────────────────────────────────────────────────────────

CLAIM = {**m1.CLAIM, "properties": {**m1.CLAIM["properties"], "type": {"type": "string", "enum": list(gd.CLAIM_TYPES)}}}
SUPPORTED = {**m1.SUPPORTED, "properties": {**m1.SUPPORTED["properties"],
                                            "type": {"type": "string", "enum": list(gd.CLAIM_TYPES)}}}
VERIFIER_SCHEMA = {**m1.VERIFIER_SCHEMA, "properties": {**m1.VERIFIER_SCHEMA["properties"],
                                                        "unsupported_claims": {"type": "array", "items": CLAIM},
                                                        "supported_claims": {"type": "array", "items": SUPPORTED}}}

VERIFIER_SYSTEM = """당신은 화장품 · 뷰티 CRM 메시지의 사실 근거를 검증하는 검수자입니다.
메시지 속 '상품 사실 주장'이 이 상품의 상품정보에 근거가 있는지 판단합니다.

정의 (사람 검수자와 같은 문장)
{definition}

작업
1. 메시지에서 정의의 9가지 유형에 해당하는 상품 사실 주장을 모두 찾습니다. 정의에서 '대상이 아닌 것'은 찾지 않습니다.
   한 주장에는 유형을 하나만 붙입니다.
2. 주장마다 상품정보와 대조합니다. 상품정보의 모든 필드를 끝까지 확인한 뒤 판단합니다.
   특성어긋남은 상품정보와 어긋날 때만 근거 없음이고, 상품정보에 없을 뿐인 일반 묘사는 아예 주장으로 올리지 않습니다.
   고객의 고민에 공감하는 말 자체는 주장이 아닙니다. 상품이 그 고민을 해결하거나 그 고민에 적합하다고 말할 때만
   근거없는고민연결로 봅니다.
   - 근거가 있으면 supported_claims 에 넣고, 근거가 된 필드 이름을 db_field 에 적습니다.
   - 근거가 없거나 내용이 다르면 unsupported_claims 에 넣습니다. db_judgment 는 '없음'(상품정보에 해당 내용이 없음)
     또는 '다름'(상품정보와 내용이 어긋남)입니다. source 는 근거가 브랜드 프로필에만 있으면 '브랜드 프로필에만 있음',
     아니면 'DB·프로필 모두 없음'입니다. closest_db_text 에는 상품정보에서 가장 가까운 문구를 그대로 옮기고, 없으면
     빈 문자열로 둡니다.
3. span 은 메시지의 해당 구간을 한 글자도 바꾸지 말고 그대로 옮깁니다(근거 없는 부분만 짧게).
4. purpose_conveyed: 메시지가 고른 발송 목적을 고객에게 전달하는지 O/X 로 답합니다.
reason 은 한국어 한 문장입니다."""


def system_text() -> str:
    return VERIFIER_SYSTEM.format(definition=gd.definition_text())


async def call(client: Any, system: str, user: str, effort: str) -> dict[str, Any]:
    """llm_review.call 과 같지만 추론 강도를 인자로 받는다(llm_review 는 고치지 않는다)."""
    last = None
    for attempt in range(4):
        t0 = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=VERIFIER_MODEL, reasoning_effort=effort,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_schema", "json_schema": {"name": "grounding_verifier_v2", "strict": True,
                                                                        "schema": VERIFIER_SCHEMA}},
            )
            return {"output": json.loads(resp.choices[0].message.content or ""), "response_id": resp.id,
                    "model": resp.model, "usage": resp.usage.model_dump() if resp.usage else None,
                    "latency_s": round(time.perf_counter() - t0, 2), "attempts": attempt + 1}
        except Exception as e:  # noqa: BLE001 — 재시도 후 결측으로 남긴다
            last = e
            if "insufficient_quota" in str(e) or "credit_balance_exhausted" in str(e):
                break  # 크레딧 소진은 재시도해도 소용없다
            await asyncio.sleep(2 ** attempt * 3)
    return {"error": f"{type(last).__name__}: {last}", "attempts": attempt + 1}


def _klass(claims: list[dict[str, Any]]) -> str:
    valid = [c for c in claims if c["span_in_message"]]
    if any(not c["auto_review"] for c in valid):
        return "양성"
    return "재검토" if valid else "음성"


def postprocess(m: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    base = m1.postprocess(m, out)  # 구간 확인 · 자동 재검토 · 특성어긋남 '없음' 제외는 v1 과 같은 규칙
    claims = base["claims"]
    primary = [c for c in claims if c["type"] in gd.PRIMARY_TYPES]
    v1types = [c for c in claims if c["type"] in gd.V1_TYPES]
    k_p, k_v1 = _klass(primary), _klass(v1types)
    return {**base,
            "class_primary": k_p, "primary_positive": k_p in ("양성", "재검토"),
            "class_v1types": k_v1, "v1types_positive": k_v1 in ("양성", "재검토"),
            "type_counts": {t: sum(1 for c in claims if c["type"] == t and c["span_in_message"]) for t in gd.CLAIM_TYPES}}


# ── 실행 ─────────────────────────────────────────────────────────────────────

async def run(messages: list[dict[str, Any]], out_dir: Path, effort: str, judge_runs: int, skip_verifier: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tones = get_brand_tones().get("brand_ton_prompt", {})
    detector = run_d1.make_detector()
    system = system_text()
    vpath = out_dir / "verifier_raw.jsonl"
    done_v = {r["item_id"]: r for r in load_jsonl(vpath) if "output" in r and r.get("effort") == effort} \
        if vpath.exists() else {}
    if not skip_verifier:
        client = llm_review.openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
        sem = asyncio.Semaphore(VERIFIER_CONCURRENCY)

        async def verify(msg: dict[str, Any]) -> None:
            async with sem:
                res = await call(client, system, m1.verifier_user(msg, str(tones.get(msg["brand"], "") or "")), effort)
            rec = {"item_id": msg["item_id"], "at": datetime.now(timezone.utc).isoformat(), "effort": effort,
                   "system_sha": llm_review.sha(system), **res}
            with open(vpath, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if "output" in rec:
                done_v[msg["item_id"]] = rec
            print(f"  검증 {msg['item_id']} {'오류' if 'error' in rec else '완료'}", flush=True)

        todo = [x for x in messages if x["item_id"] not in done_v]
        print(f"LLM 근거 검증 v2 {len(todo)}건 (모델 {VERIFIER_MODEL}, effort {effort}, 이미 한 {len(done_v)}건 건너뜀)", flush=True)
        await asyncio.gather(*(verify(x) for x in todo))

    jpath = out_dir / "judge_raw.jsonl"
    done_j = {(r["item_id"], r["run"]): r for r in load_jsonl(jpath) if not r.get("missing")} if jpath.exists() else {}
    if judge_runs:
        jsem = asyncio.Semaphore(m1.JUDGE_CONCURRENCY)

        async def one_judge(msg: dict[str, Any], k: int) -> None:
            res = await m1.judge(detector, msg, k, jsem)
            rec = {"item_id": msg["item_id"], **res}
            with open(jpath, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if not rec["missing"]:
                done_j[(msg["item_id"], k)] = rec

        jobs = [(x, k) for x in messages for k in range(1, judge_runs + 1) if (x["item_id"], k) not in done_j]
        print(f"판정기 {len(jobs)}회", flush=True)
        await asyncio.gather(*(one_judge(x, k) for x, k in jobs))

    rows = []
    usage = {"prompt": 0, "completion": 0, "reasoning": 0}
    for msg in messages:
        v = done_v.get(msg["item_id"])
        if v and v.get("usage"):
            u = v["usage"]
            usage["prompt"] += u["prompt_tokens"]
            usage["completion"] += u["completion_tokens"]
            usage["reasoning"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        rows.append({"item_id": msg["item_id"], "purpose": msg["purpose"],
                     "regex": regex_metrics_v2(msg, str(tones.get(msg["brand"], "") or "")),
                     "format": m1.format_metrics(msg, detector),
                     "verifier": postprocess(msg, v["output"]) if v else None,
                     "judge": [done_j[(msg["item_id"], k)] for k in range(1, judge_runs + 1) if (msg["item_id"], k) in done_j]})
    write_jsonl(out_dir / "measure.jsonl", rows)
    meta = {"measured_at": datetime.now(timezone.utc).isoformat(), "n": len(rows), "verifier_model": VERIFIER_MODEL,
            "verifier_effort": effort, "verifier_system_sha": llm_review.sha(system), "judge_runs": judge_runs,
            "usage": usage, "prereg_v2": gg_status(),
            "verifier_missing": [x["item_id"] for x in messages if x["item_id"] not in done_v] if not skip_verifier else "생략"}
    (out_dir / "measure_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    pos = sum(1 for r in rows if r["verifier"] and r["verifier"]["llm_positive"])
    pp = sum(1 for r in rows if r["verifier"] and r["verifier"]["primary_positive"])
    print(f"→ {out_dir / 'measure.jsonl'}  n={len(rows)} · 9유형 양성 {pos} · 주 지표 양성 {pp} · "
          f"토큰 입력 {usage['prompt']:,} 출력 {usage['completion']:,}", flush=True)


def gg_status() -> Any:
    if not vc.BASELINE_V2.exists():
        return "잠금 전"
    base = json.loads(vc.BASELINE_V2.read_text(encoding="utf-8"))
    now = vc.gg.file_hashes(vc.PREREG_V2_FILES)
    return {k: ("기준과 같음" if base.get("prereg_v2", {}).get(k) == v else "기준과 다름") for k, v in now.items()}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--messages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--effort", choices=("high", "medium", "low"), required=True)
    ap.add_argument("--judge-runs", type=int, default=0)
    ap.add_argument("--skip-verifier", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(m1.load_messages(Path(a.messages)), Path(a.out), a.effort, a.judge_runs, a.skip_verifier))


if __name__ == "__main__":
    main()
