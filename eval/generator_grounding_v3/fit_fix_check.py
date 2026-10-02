"""
v3R2 플랜 2단계 — 선호 연결 수리 후보 오프라인 점검(생성 없음) → result/dev/v3r2/fit_fix_check.{md,json}

    python fit_fix_check.py record        # 통과 기준을 AMENDMENTS 에 먼저 기록('v3R2 부품 점검 기준')
    python fit_fix_check.py a_latency     # 후보 A(연결별 근거 확인 필터, mini) 지연: fit + 필터, 10태스크 3회 중앙값
    python fit_fix_check.py a_accuracy    # 후보 A 정확도: 사람 라벨 116건(H 표본)
    python fit_fix_check.py b_proxy       # 후보 B-1: 대리 판정기(gpt-5.5 medium)를 116건 사람 라벨로 검증
    python fit_fix_check.py b_compare     # 후보 B-2: H 20항목 × (현재 · 새 fit 프롬프트) × 2회, 연결 전부를 대리 판정
    python fit_fix_check.py b_aux         # 보조(판정 아님): 개발 표본 N014 · N035 · N028 · N047 에 새 프롬프트 2회

순서: a_latency → (기준 안) a_accuracy → (A 접힘) b_proxy → (통과) b_compare. 새 fit 프롬프트는 파일을 고치지 않고
이 스크립트 안에서 SYSTEM 을 바꿔 돌린다. 정답 세트는 eval/generator_grounding_v2/result/fit_effort/irrelevant_check.csv.
"""

import asyncio
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict

import v3_common as v3
from v3_common import gg, vc
from gg_common import load_jsonl

import grounding_def_v2 as gd  # noqa: E402
import measure_v2 as mv  # noqa: E402
import llm_review  # noqa: E402

from pydantic import BaseModel  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.prompts.product_fields import generation_product_info  # noqa: E402

OUT = v3.RESULT / "dev" / "v3r2"
JS = OUT / "fit_fix_check.json"
MD = OUT / "fit_fix_check.md"
LABELS = vc.RESULT / "fit_effort" / "irrelevant_check.csv"
KIND = "v3R2 부품 점검 기준"
CRIT = {"a_latency_max_s": 5.0, "a_x_block_min": 6, "a_o_block_max": 11,
        "proxy_x_min": 6, "proxy_o_min_rate": 0.90, "b_ungrounded_max_ratio": 0.5, "b_grounded_min_ratio": 0.85}
AUX = ("N014", "N035", "N028", "N047")

NEW_SYSTEM = pf.SYSTEM.replace(
    "(제형 · 마무리감 · 흡수 · 향 · 사용감 · 용량 · 용기)",
    "(제형 · 마무리감 · 흡수 · 향 · 사용감 · 용량 · 용기 · 사용 시점 · 사용 단계)").replace(
    "   - need_type: 피부 · 모발 · 두피 · 몸의 고민이나 효능 기대는 \"concern\", 제형 · 향 · 마무리감 · 사용감 선호는 \"preference\".",
    "   - need_type: 피부 · 모발 · 두피 · 몸의 고민이나 효능 기대는 \"concern\", 제형 · 향 · 마무리감 · 사용감 선호는 \"preference\".\n"
    "   - 지속 · 내구 · 차단 · 방지처럼 효과를 기대하는 니즈는 선호가 아니라 \"concern\" 입니다.\n"
    "   - 사용 시점 · 사용 단계 선호는 상품정보에 같은 시점 · 단계가 적혀 있을 때만 넣습니다.")
assert NEW_SYSTEM.count("사용 시점 · 사용 단계") == 2 and "효과를 기대하는 니즈" in NEW_SYSTEM, "SYSTEM 치환 실패"

QUESTION = ("아래 '연결'마다, 메시지가 '이 상품이 [페르소나 니즈]에 맞다 · 도움이 된다'고 쓴다면 그 주장이 상품정보에 근거가 "
            "있는지 판정한다. 근거 문구가 상품정보에 있더라도 니즈와 같은 뜻이 아니면(다른 효과 · 다른 축 · 다른 사용 시점) "
            "근거 없음이다. 판정 정의:\n")


class LinkVerdict(BaseModel):
    idx: int
    grounded: bool


class LinkVerdicts(BaseModel):
    verdicts: list[LinkVerdict]


def _user(product: dict, links: list[dict]) -> str:
    body = "\n".join(f"{i}. 니즈({'고민' if l['type'] == 'concern' else '선호'}): {l['need']} ← 근거 문구: '{l['evidence']}'"
                     for i, l in enumerate(links))
    return ("[상품정보]\n" + json.dumps(generation_product_info(product), ensure_ascii=False, indent=1)
            + "\n\n[연결]\n" + body + "\n\n각 연결 번호(idx)마다 grounded(true/false)를 낸다.")


def _system() -> str:
    return QUESTION + gd.primary_definition_text()


async def mini_filter(product: dict, links: list[dict]) -> list[bool]:
    """후보 A: 운영에 넣을 경우의 필터(fit 과 같은 mini · 같은 추론 강도)."""
    if not links:
        return []
    llm = get_llm(settings.persona_fit_model_name or settings.chatgpt_model_name,
                  reasoning_effort=settings.persona_fit_reasoning_effort).with_structured_output(LinkVerdicts)
    out = await llm.ainvoke([("system", _system()), ("human", _user(product, links))])
    got = {v.idx: v.grounded for v in out.verdicts}
    return [got.get(i, True) for i in range(len(links))]


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdicts"],
          "properties": {"verdicts": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["idx", "grounded", "reason"],
              "properties": {"idx": {"type": "integer"}, "grounded": {"type": "boolean"}, "reason": {"type": "string"}}}}}}


async def proxy(client, product: dict, links: list[dict], sem) -> list[dict]:
    """대리 판정기: gpt-5.5 medium(검증기와 같은 모델 · 강도)."""
    if not links:
        return []
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.chat.completions.create(
                    model=mv.VERIFIER_MODEL, reasoning_effort="medium",
                    messages=[{"role": "system", "content": _system()}, {"role": "user", "content": _user(product, links)}],
                    response_format={"type": "json_schema", "json_schema": {"name": "link_proxy", "strict": True, "schema": SCHEMA}})
                got = {v["idx"]: v for v in json.loads(resp.choices[0].message.content)["verdicts"]}
                return [got.get(i, {"grounded": None, "reason": "누락"}) for i in range(len(links))]
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    return [{"grounded": None, "reason": f"오류 {type(e).__name__}"} for _ in links]
                await asyncio.sleep(2 ** attempt * 3)


def holdout() -> dict:
    return {r["item_id"]: r for r in gg.load_inputs("holdout")}


def labels() -> dict[str, list[dict]]:
    by = defaultdict(list)
    for r in csv.DictReader(open(LABELS, encoding="utf-8-sig")):
        by[r["item_id"]].append({"need": r["페르소나_고민선호"], "type": "concern" if r["종류"] == "고민" else "preference",
                                 "evidence": r["상품정보_근거"], "label": r["관련(O/X)"].strip().upper()})
    return dict(by)


def save(key: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cur = json.loads(JS.read_text(encoding="utf-8")) if JS.exists() else {}
    cur[key] = data
    JS.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    render(cur)


def render(cur: dict) -> None:
    L = ["# v3R2 선호 연결 수리 후보 오프라인 점검", "", f"- 기준(AMENDMENTS '{KIND}'): `{json.dumps(CRIT, ensure_ascii=False)}`", ""]
    for k, v in cur.items():
        L += [f"## {k}", "", "```json", json.dumps({x: y for x, y in v.items() if x != "rows"}, ensure_ascii=False, indent=2), "```", ""]
        for r in v.get("rows", [])[:400]:
            L.append(f"- {r}")
        L.append("")
    MD.write_text("\n".join(L) + "\n", encoding="utf-8")


def guard() -> None:
    if not any(e["kind"] == KIND for e in gg.amendments_entries()):
        raise SystemExit("기준 기록이 먼저다: python fit_fix_check.py record")


def record() -> None:
    if any(e["kind"] == KIND for e in gg.amendments_entries()):
        raise SystemExit("이미 기록됨")
    content = ("v3R2 플랜(최종 측정 전 마지막 개선 시도) 2단계 통과 기준, 결과 보기 전 기록. 정답 세트: 사람 라벨 116건(H 표본 20항목, "
               "O 108 · X 8). 후보 A(연결별 근거 확인 필터, mini): fit + 필터 10태스크 지연 ≤ +5.0초(넘으면 정확도는 재지 않음), "
               "X 차단 ≥ 6/8, O 오차단 ≤ 11/108. 후보 B-1(대리 판정기 gpt-5.5 medium): X 중 근거 없음 ≥ 6/8, O 중 근거 있음 ≥ 90%. "
               "후보 B-2(fit 프롬프트: 같은 축에 사용 시점 · 단계 추가, 지속 · 내구 · 차단 기대는 concern): H 20항목 × 현재 · 새 × 2회 "
               "연결 전부 대리 판정, 새 프롬프트 근거 없음 연결 수 ≤ 현재의 0.5배, 근거 있음 연결 수 ≥ 현재의 0.85배. "
               "순서 A 지연 → A 정확도 → B-1 → B-2, 하나만 채택. 둘 다 미달이면 v3R2 를 만들지 않고 v3R 로 최종 측정. "
               f"새 SYSTEM sha256={hashlib.sha256(NEW_SYSTEM.encode()).hexdigest()}")
    gg.append_amendment(KIND, content, {})
    print("기록함")


async def _a_latency() -> None:
    guard()
    its = load_jsonl(vc.RESULT / "main" / "inputs.jsonl")[:10]
    fitter = pf.PersonaFitter()

    async def one(it):
        f = await fitter.fit(it["persona_info"], it["product_snapshot"])
        links = [{"need": c["persona_need"], "type": c["need_type"], "evidence": c["product_evidence"]} for c in f.connectable]
        t = time.perf_counter()
        await mini_filter(it["product_snapshot"], links)
        return time.perf_counter() - t

    tot, filt = [], []
    for _ in range(3):
        t0 = time.perf_counter()
        fs = await asyncio.gather(*(one(it) for it in its))
        tot.append(time.perf_counter() - t0)
        filt.append(statistics.median(fs))
    data = {"fit_plus_filter_median_10_s": round(statistics.median(tot), 2),
            "filter_only_item_median_s": round(statistics.median(filt), 2),
            "pass": statistics.median(tot) <= CRIT["a_latency_max_s"]}
    save("A_latency", data)
    print(data)


async def _a_accuracy() -> None:
    guard()
    H, LB = holdout(), labels()
    res = await asyncio.gather(*(mini_filter(H[i]["product_snapshot"], ls) for i, ls in LB.items()))
    rows, xb, ob = [], 0, 0
    for (i, ls), vs in zip(LB.items(), res):
        for l, g in zip(ls, vs):
            xb += l["label"] == "X" and not g
            ob += l["label"] == "O" and not g
            if (l["label"] == "X") or not g:
                rows.append(f"{i} {l['need']} ← '{l['evidence'][:40]}' 사람 {l['label']} · 필터 {'통과' if g else '차단'}")
    data = {"x_blocked": xb, "o_blocked": ob, "pass": xb >= CRIT["a_x_block_min"] and ob <= CRIT["a_o_block_max"], "rows": rows}
    save("A_accuracy", data)
    print({k: v for k, v in data.items() if k != "rows"})


async def _b_proxy() -> None:
    guard()
    H, LB = holdout(), labels()
    client = llm_review.openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
    sem = asyncio.Semaphore(6)
    res = await asyncio.gather(*(proxy(client, H[i]["product_snapshot"], ls, sem) for i, ls in LB.items()))
    rows, xu, og, miss = [], 0, 0, 0
    for (i, ls), vs in zip(LB.items(), res):
        for l, v in zip(ls, vs):
            if v["grounded"] is None:
                miss += 1
                continue
            xu += l["label"] == "X" and not v["grounded"]
            og += l["label"] == "O" and v["grounded"]
            if (l["label"] == "X") == v["grounded"]:  # 불일치만
                rows.append(f"{i} {l['need']} ← '{l['evidence'][:40]}' 사람 {l['label']} · 대리 {'근거 있음' if v['grounded'] else '근거 없음'} — {v['reason'][:80]}")
    n_o = sum(l["label"] == "O" for ls in LB.values() for l in ls)
    data = {"x_ungrounded": xu, "o_grounded": og, "n_o": n_o, "missing": miss,
            "pass": xu >= CRIT["proxy_x_min"] and og >= CRIT["proxy_o_min_rate"] * n_o, "disagreements": len(rows), "rows": rows}
    save("B1_proxy", data)
    print({k: v for k, v in data.items() if k != "rows"})


async def _fit_runs(items: dict, system: str, runs: int) -> list[tuple]:
    old = pf.SYSTEM
    pf.SYSTEM = system  # PersonaFitter.fit 은 모듈 전역 SYSTEM 을 쓴다(파일은 고치지 않음)
    try:
        fitter, sem = pf.PersonaFitter(), asyncio.Semaphore(8)

        async def one(iid, run):
            async with sem:
                f = await fitter.fit(items[iid]["persona_info"], items[iid]["product_snapshot"])
            return iid, run, f
        return await asyncio.gather(*(one(i, r) for i in items for r in range(1, runs + 1)))
    finally:
        pf.SYSTEM = old


async def _b_compare(items: dict, key: str) -> None:
    client = llm_review.openai.AsyncOpenAI(api_key=settings.openai_api_key, timeout=600)
    sem = asyncio.Semaphore(6)
    out, rows = {}, []
    for name, system in (("current", pf.SYSTEM), ("new", NEW_SYSTEM)):
        fits = await _fit_runs(items, system, 2)
        links = [[{"need": c["persona_need"], "type": c["need_type"], "evidence": c["product_evidence"]} for c in f.connectable]
                 for _, _, f in fits]
        vs = await asyncio.gather(*(proxy(client, items[i]["product_snapshot"], ls, sem) for (i, _, _), ls in zip(fits, links)))
        tot = sum(len(ls) for ls in links)
        ung = sum(1 for v in vs for x in v if x["grounded"] is False)
        grd = sum(1 for v in vs for x in v if x["grounded"] is True)
        typ = {t: sum(1 for ls in links for l in ls if l["type"] == t) for t in ("concern", "preference")}
        zero = sum(1 for _, _, f in fits if not any(c["need_type"] == "concern" for c in f.connectable))
        out[name] = {"links": tot, "ungrounded": ung, "grounded": grd, "by_type": typ, "zero_concern_runs": zero,
                     "fit_ok": sum(f.status == "ok" for _, _, f in fits), "runs": len(fits)}
        for (i, r, _), ls, v in zip(fits, links, vs):
            rows += [f"{name} {i}#{r} [{'고민' if l['type'] == 'concern' else '선호'}] {l['need']} ← '{l['evidence'][:40]}' → "
                     f"{'근거 없음' if x['grounded'] is False else '근거 있음' if x['grounded'] else '누락'}"
                     for l, x in zip(ls, v) if x["grounded"] is not True]
    c, n = out["current"], out["new"]
    out["pass"] = (n["ungrounded"] <= CRIT["b_ungrounded_max_ratio"] * c["ungrounded"]
                   and n["grounded"] >= CRIT["b_grounded_min_ratio"] * c["grounded"])
    out["rows"] = rows
    save(key, out)
    print({k: v for k, v in out.items() if k != "rows"})


async def _b_compare_h() -> None:
    guard()
    js = json.loads(JS.read_text(encoding="utf-8")) if JS.exists() else {}
    if not js.get("B1_proxy", {}).get("pass"):
        raise SystemExit("B-1 대리 판정기 검증을 통과해야 B-2 를 돈다")
    H, LB = holdout(), labels()
    await _b_compare({i: H[i] for i in LB}, "B2_compare_H")


async def _b_aux() -> None:
    guard()
    dev = {r["item_id"]: r for r in load_jsonl(vc.RESULT / "main" / "inputs.jsonl") if r["item_id"] in AUX}
    await _b_compare(dev, "B_aux_dev4(판정 아님)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "record":
        record()
    else:
        asyncio.run({"a_latency": _a_latency, "a_accuracy": _a_accuracy, "b_proxy": _b_proxy,
                     "b_compare": _b_compare_h, "b_aux": _b_aux}[cmd]())


if __name__ == "__main__":
    main()
