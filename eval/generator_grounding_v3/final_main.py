"""
최종 측정 — 초기(v0) 대 최종 버전, 한 번만 (PREREG_final.md).

    python final_main.py lock                 # 단계 0: 측정 도구 · 사전 등록 해시 잠금 → baseline_final.json + AMENDMENTS
    python final_main.py check                # 잠금 대조(마지막 AMENDMENTS 기록 기준)
    python final_main.py sample               # 단계 0: 표본 70건(시드 20261011, Docker 필요) → result/final/inputs.jsonl
    python final_main.py gen --cond v0        # 단계 0: v0 생성(e967b13 프롬프트, fitter 없음). 내용은 출력하지 않는다(눈가림)
    python final_main.py gen --cond final     # 단계 4: 'AMENDMENTS 최종 버전 확정' 기록과 해시가 같을 때만
    python final_main.py measure              # 단계 4: v0 · 최종을 같은 시점에 검증기 medium + 판정기 2회
    python final_main.py report               # 단계 4: result/final/report_final.md (사람 확인 결과가 있으면 반영)

잠금 파일 수정은 측정 결과를 보기 전에만, 사유 · diff 요약 · 새 해시를 AMENDMENTS('최종 측정 도구 수정')에 남긴다.
"""

import argparse
import asyncio
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from typing import Any

import v3_common as v3
from v3_common import gg, vc
from gg_common import load_jsonl, write_jsonl

import sample_holdout as sh  # noqa: E402
from _common import load_personas, persona_info  # noqa: E402

FINAL = v3.FINAL
SEED = 20261011
N = 70
MIN_N = 60
VERIFIER_EFFORT = "medium"
JUDGE_RUNS = 2
CI = 0.95
BOOT_SEED, BOOT_REPS = 20261003, 10_000
STRATA = ("양성", "재검토", "음성")
NI = {"pass_rate": -0.15, "personalization": -0.3, "cta_clarity": -0.3, "tone": -0.3, "accuracy": -0.3,
      "purpose_conveyed": -0.15}
TOOL_FILES = [vc.HERE / "grounding_def_v2.py", vc.HERE / "measure_v2.py", v3.HERE / "v3_common.py",
              v3.HERE / "final_main.py", v3.HERE / "human_final.py", v3.HERE / "check_tool_final.py",
              v3.HERE / "check_tool_final_ui.html", v3.PREREG_FINAL]
FINAL_VERSION_FILES = [gg.PURPOSE_PROMPT, vc.PERSONA_FIT, gg.PRODUCT_FIELDS, v3.GEN_CRM]
KIND_LOCK, KIND_TOOL_FIX, KIND_FINAL_VERSION = "최종 측정 잠금", "최종 측정 도구 수정", "최종 버전 확정"


def rel(p) -> str:
    return p.resolve().relative_to(gg.REPO).as_posix()


# ── 잠금 ─────────────────────────────────────────────────────────────────────

def lock() -> None:
    if v3.BASELINE_FINAL.exists():
        raise SystemExit("이미 잠겼습니다. 수정은 AMENDMENTS('최종 측정 도구 수정')로 한다")
    import measure_v2 as mv
    from app.config.settings import settings
    hashes = {rel(p): gg.sha256(p) for p in TOOL_FILES}
    base = {"locked_at": datetime.now(timezone.utc).isoformat(), "tools": hashes,
            "verifier": {"model": mv.VERIFIER_MODEL, "effort": VERIFIER_EFFORT},
            "judge": {"model": settings.chatgpt_model_name, "runs": JUDGE_RUNS},
            "v0": {"commit": v3.V0_COMMIT, "purpose_prompt_sha": v3.v0_sha()},
            "sample": {"seed": SEED, "n": N, "min_n": MIN_N}}
    v3.BASELINE_FINAL.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    gg.append_amendment(KIND_LOCK, "최종 측정(v0 대 최종 버전) 사전 등록 · 측정 도구 잠금. PREREG_final.md 참고",
                        {**hashes, rel(v3.BASELINE_FINAL): gg.sha256(v3.BASELINE_FINAL)})
    print(json.dumps(base, ensure_ascii=False, indent=2))


def expected_tool_hashes() -> dict[str, str]:
    base = json.loads(v3.BASELINE_FINAL.read_text(encoding="utf-8"))
    exp = dict(base["tools"])
    for e in gg.amendments_entries():
        if e["kind"] == KIND_TOOL_FIX:
            exp.update({k: v for k, v in e.get("new_hashes", {}).items() if k in exp})
    return exp


def check_lock(strict: bool = True) -> list[str]:
    if not v3.BASELINE_FINAL.exists():
        raise SystemExit("baseline_final.json 없음 — lock 을 먼저 한다")
    exp = expected_tool_hashes()
    now = {rel(p): gg.sha256(p) for p in TOOL_FILES}
    bad = [k for k in exp if now.get(k) != exp[k]]
    if bad and strict:
        raise SystemExit(f"잠금과 다른 측정 도구 파일(기록 없는 변경): {bad}")
    return bad


def final_version() -> dict[str, Any]:
    entries = [e for e in gg.amendments_entries() if e["kind"] == KIND_FINAL_VERSION]
    if not entries:
        raise SystemExit("AMENDMENTS 에 '최종 버전 확정' 기록이 없습니다")
    e = entries[-1]
    return {"version": json.loads(e["content"])["version"], "hashes": e["new_hashes"], "entry": e["id"]}


# ── 표본 ─────────────────────────────────────────────────────────────────────

def dev_personas() -> set[str]:
    return {r["persona_id"] for r in load_jsonl(vc.RESULT / "main" / "inputs.jsonl")}


def sample() -> None:
    check_lock()
    out = FINAL / "inputs.jsonl"
    if out.exists():
        raise SystemExit(f"{out} 이 이미 있습니다")
    exclude = sh._original_products() | {r["product_id"] for r in gg.load_inputs("holdout")} \
        | {r["product_id"] for r in load_jsonl(vc.RESULT / "main" / "inputs.jsonl")}
    n_excluded, failed = len(exclude), set()
    for _ in range(6):
        samples = sh.sample(N, SEED, exclude | failed, "F", strict=False)
        fetched = asyncio.run(sh._fetch([s["product_id"] for s in samples]))
        miss = {s["product_id"] for s in samples if s["product_id"] not in fetched}
        if not miss:
            break
        failed |= miss
    else:
        raise SystemExit(f"스냅숏 조회 실패가 계속됩니다: {sorted(failed)[:10]}")
    personas = load_personas()
    rows = [{**s, "persona_info": persona_info(personas[s["persona_id"]]),
             "product_snapshot": json.loads(json.dumps(fetched[s["product_id"]], ensure_ascii=False))} for s in samples]
    FINAL.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, rows)
    dev = dev_personas()
    overlap = sum(1 for r in rows if r["persona_id"] in dev)
    note = f"n={len(rows)}(시드 {SEED}, 상품 {n_excluded}개 제외, 조회 실패로 뺀 상품 {len(failed)}개), 개발 표본과 겹치는 페르소나 {overlap}건"
    if len(rows) < MIN_N:
        note += f" — {MIN_N}건 미만: 그대로 진행하고 CI 가 넓어짐을 보고한다(PREREG_final 2절)"
    gg.append_amendment("최종 측정 표본", note, {rel(out): gg.sha256(out)})
    print(note)


# ── 생성 ─────────────────────────────────────────────────────────────────────

def make_generator(cond: str):
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    if cond == "v0":
        gen = CrmMessageGenerator()
        pp = v3.git_prompt_module(v3.V0_COMMIT, v3.v0_sha(), "purpose_prompt_v0")
        gen._purpose_prompt_map = {p: getattr(pp, b) for p, b in v3.PURPOSE_BUILDERS.items()}
        return gen, f"v0({v3.V0_COMMIT})"
    fv = final_version()
    if fv["version"] == "v1":
        gen = CrmMessageGenerator()
        pp = v3.git_prompt_module(v3.V1_COMMIT, v3.v1_sha(), "purpose_prompt_v1")
        gen._purpose_prompt_map = {p: getattr(pp, b) for p, b in v3.PURPOSE_BUILDERS.items()}
        return gen, f"final=v1({v3.V1_COMMIT})"
    now = {rel(p): gg.sha256(p) for p in FINAL_VERSION_FILES}
    bad = [k for k, v in fv["hashes"].items() if now.get(k) != v]
    if bad:
        raise SystemExit(f"최종 버전 확정 기록(AMENDMENTS {fv['entry']})과 다른 파일: {bad}")
    from app.agents.generate_message_agent.prompts.persona_fit import PersonaFitter
    return CrmMessageGenerator(persona_fitter=PersonaFitter()), f"final={fv['version']}(AMENDMENTS {fv['entry']})"


async def _gen(cond: str) -> None:
    check_lock()
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.nodes import _parse_message
    items = load_jsonl(FINAL / "inputs.jsonl")
    gen, label = make_generator(cond)
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    out_dir = FINAL / cond
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "messages.jsonl"
    done = {r["item_id"] for r in load_jsonl(out)} if out.exists() else set()
    lock_ = asyncio.Lock()
    sem = asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            t0 = time.perf_counter()
            tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
            tasks = await gen.get_brand_tone(tasks)
            tasks = await gen.get_crm_prompt(tasks, persona_info=it["persona_info"])
            g = await gen.generate_crm_message(tasks, llm)
            dt = round(time.perf_counter() - t0, 2)
        if not g:
            return
        raw = g[0]["message"]
        content = raw.content if hasattr(raw, "content") else str(raw)
        msg = _parse_message(raw)
        try:
            ok = isinstance(json.loads(content), dict)
        except Exception:
            ok = False
        row = {**it, "tag": cond, "title": msg.get("title", ""), "message": msg.get("message", ""), "json_ok": ok,
               "fit_status": tasks[0].get("fit_status"), "fit_recheck": g[0].get("fit_recheck", tasks[0].get("fit_recheck")),
               "generation": {"version": label, "model": settings.chatgpt_model_name, "latency_s": dt,
                              "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock_:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    todo = [it for it in items if it["item_id"] not in done]
    print(f"{cond} [{label}]: 생성 {len(todo)}건(이미 {len(done)}건)", flush=True)
    await asyncio.gather(*(one(it) for it in todo))
    rows = {r["item_id"]: r for r in load_jsonl(out)}
    write_jsonl(out, [rows[it["item_id"]] for it in items if it["item_id"] in rows])
    # 형식만 확인한다(내용은 출력하지 않음 — 눈가림)
    import measure as m1
    import run_d1
    det = run_d1.make_detector()
    fm = [m1.format_metrics(r, det) for r in rows.values()]
    print(f"→ {out} {len(rows)}/{len(items)} · JSON 정상 {sum(r['json_ok'] for r in rows.values())} · "
          f"제목/본문 비지 않음 {sum(1 for r in rows.values() if r['title'] and r['message'])} · CTA 마지막 {sum(f['cta_last'] for f in fm)} · "
          f"fit_status {dict((s, sum(r.get('fit_status') == s for r in rows.values())) for s in ('ok', 'fallback', 'disabled'))}")


# ── 측정 ─────────────────────────────────────────────────────────────────────

async def _measure() -> None:
    check_lock()
    import measure_v2 as mv
    import measure as m1
    items = {r["item_id"] for r in load_jsonl(FINAL / "inputs.jsonl")}
    for cond in ("v0", "final"):
        have = {r["item_id"] for r in load_jsonl(FINAL / cond / "messages.jsonl")}
        if have != items:
            raise SystemExit(f"{cond} 메시지가 입력과 다릅니다(없음 {len(items - have)}건) — 생성을 끝낸 뒤 측정한다")
    for cond in ("v0", "final"):
        await mv.run(m1.load_messages(FINAL / cond / "messages.jsonl"), FINAL / cond, VERIFIER_EFFORT, JUDGE_RUNS, False)


# ── 보고서 ───────────────────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if not n:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def weighted(sizes: dict[str, int], samples: dict[str, list[int]]) -> float:
    n = sum(sizes.values())
    if not n:
        return float("nan")
    s = 0.0
    for h, k in sizes.items():
        if k:
            v = samples.get(h) or []
            if not v:
                return float("nan")  # 확인하지 않은 층이 있으면 계산하지 않는다(PREREG_final 6절)
            s += k * sum(v) / len(v)
    return s / n


def weighted_ci(sizes: dict[str, dict[str, int]], samples: dict[str, dict[str, list[int]]]) -> dict[str, Any]:
    """조건별 사람 반영 비율 · 층별 부트스트랩 95% CI · 최종 − v0 차이의 CI."""
    import report as r1
    point = {c: weighted(sizes[c], samples[c]) for c in sizes}
    rng = random.Random(BOOT_SEED)
    boots: dict[str, list[float]] = {c: [] for c in sizes}
    diffs = []
    for _ in range(BOOT_REPS):
        r = {}
        for c in sizes:
            res = {h: [rng.choice(v) for _ in v] for h, v in samples[c].items() if v}
            r[c] = weighted(sizes[c], res)
            boots[c].append(r[c])
        diffs.append(r["final"] - r["v0"])
    lo, hi = (1 - CI) / 2, 1 - (1 - CI) / 2
    return {"point": point, "ci": {c: (r1.percentile(boots[c], lo), r1.percentile(boots[c], hi)) for c in sizes},
            "diff": point["final"] - point["v0"], "diff_ci": (r1.percentile(diffs, lo), r1.percentile(diffs, hi))}


def report() -> None:
    import report as r1
    bad = check_lock(strict=False)
    M = {c: {r["item_id"]: r for r in load_jsonl(FINAL / c / "measure.jsonl")} for c in ("v0", "final")}
    msgs = {c: {r["item_id"]: r for r in load_jsonl(FINAL / c / "messages.jsonl")} for c in ("v0", "final")}
    inputs = {r["item_id"]: r for r in load_jsonl(FINAL / "inputs.jsonl")}
    ids = sorted(i for i in inputs if M["v0"].get(i, {}).get("verifier") and M["final"].get(i, {}).get("verifier"))
    n = len(ids)
    try:
        fv = final_version()
    except SystemExit:
        fv = {"version": "?", "entry": "-"}
    L = ["# 최종 측정 보고서 — 초기(v0) 대 최종 버전", "",
         f"- 작성: {datetime.now(timezone.utc).isoformat()} · 짝 {n}건 · 최종 버전: {fv['version']} (AMENDMENTS {fv['entry']})",
         f"- 측정 도구 잠금 대조: {'마지막 기록과 같음' if not bad else '기록 없는 변경 ' + str(bad) + ' → 이 보고서는 탐색적'}",
         "- 사전 등록: PREREG_final.md (한 번만 측정)", ""]
    if fv["version"] == "v1":
        L += ["> 이 경우 최종 결과는 1라운드 수정만의 효과이며 v2 · v3는 채택하지 않았다.", ""]
    if n < MIN_N:
        L += [f"> 짝 {n}건 — {MIN_N}건 미만이라 CI 가 넓다.", ""]

    def block(key: str, cls_key: str, title: str, human_key: str) -> None:
        pos = {c: [i for i in ids if M[c][i]["verifier"][cls_key] in ("양성", "재검토")] for c in M}
        b = sum(1 for i in ids if i in pos["v0"] and i not in pos["final"])
        cc = sum(1 for i in ids if i not in pos["v0"] and i in pos["final"])
        t = r1.paired_test(b, cc)
        ci = {c: wilson(len(pos[c]), n) for c in M}
        L.extend([f"## {title}", "", "| | v0 | 최종 |", "|---|---|---|",
                  "| LLM 양성(재검토 포함) | " + " | ".join(f"{len(pos[c])}/{n} = {len(pos[c]) / n:.1%} (95% CI {ci[c][0]:.1%}~{ci[c][1]:.1%})" for c in M) + " |",
                  "| LLM 층(양성 · 재검토 · 음성) | " + " | ".join(" · ".join(str(sum(1 for i in ids if M[c][i]['verifier'][cls_key] == h)) for h in STRATA) for c in M) + " |"])
        H = HUMAN_RES.get(human_key) if HUMAN_RES else None
        if H:
            sizes = {c: {h: sum(1 for i in ids if M[c][i]["verifier"]["class"] == h) for h in STRATA} for c in M}
            w = weighted_ci(sizes, {c: H.get(c, {}) for c in M})
            L.append("| 사람 확인 반영 | " + " | ".join(f"{w['point'][c]:.1%} (95% CI {w['ci'][c][0]:.1%}~{w['ci'][c][1]:.1%})" for c in M) + " |")
            L.append("| 사람 확인 O/확인 (층별) | " + " | ".join(", ".join(f"{h} {sum(H[c][h])}/{len(H[c][h])}" for h in STRATA if H.get(c, {}).get(h)) for c in M) + " |")
            L.append(f"\n- 사람 확인 반영 차이(최종 − v0): {w['diff']:+.1%} (95% CI {w['diff_ci'][0]:+.1%}~{w['diff_ci'][1]:+.1%})")
            SUMMARY[key] = {"llm": {c: len(pos[c]) / n for c in M}, "llm_ci": ci, "human": w}
        else:
            SUMMARY[key] = {"llm": {c: len(pos[c]) / n for c in M}, "llm_ci": ci, "human": None}
            L.append("\n- 사람 확인 결과 없음(아직)")
        L.extend([f"- 짝 비교 v0 → 최종: 개선 {b} · 악화 {cc}, {t['method']} p = {t['p']:.4f}", ""])

    block("headline", "class", "헤드라인 — 근거 없는 상품 주장(9개 유형)이 1개 이상인 메시지", "headline")
    block("primary", "class_primary", "보조 — 주 지표(특성어긋남 · 근거없는고민연결)", "primary")

    import grounding_def_v2 as gd
    L += ["## 유형별 (LLM 클레임이 있는 메시지 수)", "", "| 유형 | v0 | 최종 |", "|---|---|---|"]
    for t in gd.CLAIM_TYPES:
        L.append(f"| {t} | " + " | ".join(str(sum(1 for i in ids if M[c][i]["verifier"]["type_counts"].get(t))) for c in M) + " |")
    L.append("")

    # 비열등
    L += ["## 품질 유지(비열등, v0 대비 짝 부트스트랩 단측 95% 하한)", "", "| 지표 | v0 | 최종 | 차이 | 하한 | 여유 | 판정 |", "|---|---|---|---|---|---|---|"]
    ok_all = True
    jb = {i: r1.item_judge(M["v0"][i]) for i in ids}
    ja = {i: r1.item_judge(M["final"][i]) for i in ids}
    jid = [i for i in ids if jb[i] and ja[i]]
    for k, margin in NI.items():
        if k == "purpose_conveyed":
            vb = {i: 1.0 if M["v0"][i]["verifier"]["purpose_conveyed"] == "O" else 0.0 for i in ids}
            va = {i: 1.0 if M["final"][i]["verifier"]["purpose_conveyed"] == "O" else 0.0 for i in ids}
            use = ids
        else:
            vb, va, use = {i: jb[i][k] for i in jid}, {i: ja[i][k] for i in jid}, jid
        d, lo = r1.paired_boot_lower([va[i] - vb[i] for i in use])
        ok = lo >= margin
        ok_all &= ok
        L.append(f"| {k} | {sum(vb[i] for i in use) / len(use):.3f} | {sum(va[i] for i in use) / len(use):.3f} | {d:+.3f} | {lo:+.3f} | {margin} | {'통과' if ok else '미달'} |")
    L += ["", f"- 결론: {'품질 유지 확인(모든 지표 비열등 통과)' if ok_all else '품질 유지는 확인하지 못했다(미달 지표 수치만 보고)'}", ""]

    # 페르소나 중복
    dev = dev_personas()
    ov = [i for i in ids if inputs[i]["persona_id"] in dev]
    nov = [i for i in ids if i not in ov]
    L += ["## 페르소나 중복(개발 표본 = 2라운드 새 표본 70건)", "",
          f"- 겹치는 페르소나의 항목 {len(ov)}/{n}"]
    for name, grp in (("겹침", ov), ("안 겹침", nov)):
        if grp:
            L.append(f"- {name} {len(grp)}건: LLM 헤드라인 v0 " +
                     f"{sum(1 for i in grp if M['v0'][i]['verifier']['class'] in ('양성', '재검토')) / len(grp):.1%} → 최종 "
                     f"{sum(1 for i in grp if M['final'][i]['verifier']['class'] in ('양성', '재검토')) / len(grp):.1%}")
    L.append("")

    # 생성 정보
    fr = [msgs["final"][i].get("fit_recheck") for i in ids]
    L += ["## 생성 정보", "",
          f"- 최종 fit_status: {dict((s, sum(msgs['final'][i].get('fit_status') == s for i in ids)) for s in ('ok', 'fallback', 'disabled'))}",
          f"- 최종 fit_recheck: {dict((s, fr.count(s)) for s in sorted({x for x in fr if x}))}",
          "- 1라운드 사람 확인의 음성 층(수정 전 0/10 · 수정 후 0/10)은 검증기 설정이 달라(high · 8개 유형) 참고값으로만 인용한다.", ""]

    # 보고 문구
    h = SUMMARY["headline"]
    line1 = f"LLM 기준 초기 {h['llm']['v0']:.1%} → 최종 {h['llm']['final']:.1%} (각 {n}건, 같은 입력, 95% CI {h['llm_ci']['v0'][0]:.1%}~{h['llm_ci']['v0'][1]:.1%} / {h['llm_ci']['final'][0]:.1%}~{h['llm_ci']['final'][1]:.1%})"
    L += ["## 보고 문구(사전 등록 형식)", "", f"- {line1}"]
    if h["human"]:
        w = h["human"]
        L.append(f"- 사람 확인 반영 시 초기 {w['point']['v0']:.1%} (CI {w['ci']['v0'][0]:.1%}~{w['ci']['v0'][1]:.1%}) → "
                 f"최종 {w['point']['final']:.1%} (CI {w['ci']['final'][0]:.1%}~{w['ci']['final'][1]:.1%})")
    out = FINAL / "report_final.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {out}")


HUMAN_RES: dict[str, Any] | None = None
SUMMARY: dict[str, Any] = {}


def main() -> None:
    global HUMAN_RES
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("lock", "check", "sample", "gen", "measure", "report"))
    ap.add_argument("--cond", choices=("v0", "final"))
    a = ap.parse_args()
    if a.cmd == "lock":
        lock()
    elif a.cmd == "check":
        bad = check_lock(strict=False)
        print("잠금과 같음(마지막 기록 기준)" if not bad else f"기록 없는 변경: {bad}")
    elif a.cmd == "sample":
        sample()
    elif a.cmd == "gen":
        if not a.cond:
            raise SystemExit("--cond v0 | final")
        asyncio.run(_gen(a.cond))
    elif a.cmd == "measure":
        asyncio.run(_measure())
    else:
        import human_final as hf
        HUMAN_RES = hf.results() if (hf.HUMAN / "sample_map.json").exists() and (hf.HUMAN / "human_check.csv").exists() else None
        report()


if __name__ == "__main__":
    main()
