"""
판정력 사전 계산 (3단계, 잠금 전) — v1 메시지의 주 지표 기저율과 검출 가능한 최소 효과.

    python precompute_v2.py fit        # 보류 v1 70건 입력에 fit + 40건 재실행(재현성, 한계 보고용)
    python precompute_v2.py verify     # 보류 v1 70건 메시지를 검증기 v2(medium)로 측정
    python precompute_v2.py power      # 기저율 · 정밀도 가정 · 최소 효과 → result/precompute/power.json

사용자 결정(AMENDMENTS 3번)으로 군 구분이 없으므로 전체 70건이 대상이다.
최소 효과: 주 지표(LLM 판정, 재검토 포함 양성)의 짝 비교(정확 이항 / McNemar, α=0.05) 검정력 80%를 시뮬레이션으로 구한다.
  - 참 양성률 t = LLM 양성률 × 정밀도, LLM 양성 = 참 양성(재현율 1) + 오탐(조건마다 독립, 비율 고정)
  - 수정 후 참 양성은 수정 전 참 양성 중 (1 − d)만 남는다고 둔다(새로 생기는 결함 없음 — 낙관적 가정, 보고서에 표기)
  - 정밀도는 최악 · 최선(1라운드 사람 판정에서 얻은 95% 구간 양끝)으로 두 번 계산한다. 격하 판단은 최악 기준.
"""

import asyncio
import json
import math
import random
import sys

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

OUT = vc.RESULT / "precompute"
N_RERUN, SEED = 40, 20261008
ALPHA, POWER, SIMS = 0.05, 0.8, 3000


async def fit() -> None:
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    items = load_jsonl(vc.gg.RESULT / "holdout" / "inputs.jsonl")
    fitter = pf.PersonaFitter()
    sem = asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            r = await fitter.fit(it["persona_info"], it["product_snapshot"])
            return {"item_id": it["item_id"], **r.to_dict()}

    first = await asyncio.gather(*(one(it) for it in items))
    rerun_ids = set(random.Random(SEED).sample([it["item_id"] for it in items], N_RERUN))
    second = await asyncio.gather(*(one(it) for it in items if it["item_id"] in rerun_ids))
    OUT.mkdir(exist_ok=True)
    write_jsonl(OUT / "fit_v1pool.jsonl", first)
    write_jsonl(OUT / "fit_rerun.jsonl", second)
    a = {r["item_id"]: r for r in first}
    risky = lambda r: bool(r["not_connectable"] or r["conflicts"])  # noqa: E731
    agree = sum(risky(a[r["item_id"]]) == risky(r) for r in second)
    jac = []
    for r in second:
        s1 = {c["persona_need"] for c in a[r["item_id"]]["connectable"]}
        s2 = {c["persona_need"] for c in r["connectable"]}
        jac.append(len(s1 & s2) / len(s1 | s2) if s1 | s2 else 1.0)
    stats = {"n": len(first), "risky": sum(risky(r) for r in first),
             "fallback": sum(r["status"] != "ok" for r in first),
             "rerun_n": len(second), "risky_agreement": agree / len(second),
             "connectable_need_jaccard_mean": round(sum(jac) / len(jac), 3)}
    (OUT / "fit_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(stats)


async def verify() -> None:
    import measure_v2 as mv
    msgs = mv.m1.load_messages(vc.gg.RESULT / "holdout" / "after" / "messages.jsonl")
    await mv.run(msgs, OUT / "v1_holdout", "medium", 0, False)


def _pval(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    if n < 25:
        k = min(b, c)
        return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    x = (abs(b - c) - 1) ** 2 / n
    return math.erfc(math.sqrt(x / 2))


def _power(n: int, t: float, fp: float, d: float, rng: random.Random) -> float:
    hits = 0
    q = fp / (1 - t) if t < 1 else 0.0  # 참 음성 안에서의 오탐 확률
    for _ in range(SIMS):
        b = c = 0
        for _ in range(n):
            tb = rng.random() < t
            ta = tb and rng.random() < (1 - d)
            lb = tb or rng.random() < q
            la = ta or rng.random() < q
            b += lb and not la
            c += la and not lb
        hits += _pval(b, c) < ALPHA
    return hits / SIMS


def _min_effect(n: int, t: float, fp: float) -> float | None:
    rng = random.Random(SEED)
    for d in [x / 20 for x in range(1, 21)]:
        if _power(n, t, fp, d, rng) >= POWER:
            return d
    return None


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, c - h), min(1.0, c + h)


def power() -> None:
    rows = load_jsonl(OUT / "v1_holdout" / "measure.jsonl")
    ok = [r for r in rows if r["verifier"]]
    n = len(ok)
    p_llm = sum(r["verifier"]["primary_positive"] for r in ok) / n
    # 정밀도 근거: 1라운드 사람 판정이 있는 v1(수정 후) 메시지 중 v2 주 지표 양성인 것 — 사람 O 비율
    import csv
    mp = json.loads((vc.gg.RESULT / "human" / "sample_map.json").read_text(encoding="utf-8"))
    hc = {r["code"]: r for r in csv.DictReader(open(vc.gg.RESULT / "human" / "human_check.csv", encoding="utf-8-sig"))}
    by_item = {r["item_id"]: r for r in ok}
    k = m = 0
    for code, info in mp.items():
        if info["tag"] != "after" or info["item_id"] not in by_item:
            continue
        if by_item[info["item_id"]]["verifier"]["primary_positive"]:
            m += 1
            k += hc[code]["unsupported_claim(O/X)"] == "O"
    lo, hi = _wilson(k, m)
    out = {"n": n, "llm_primary_rate": round(p_llm, 3), "calibration": {"human_O": k, "of_llm_positive": m,
                                                                         "precision_95": [round(lo, 3), round(hi, 3)]},
           "note": "1라운드 사람 판정은 v1 정의(8개 유형) 기준이라 새 유형(고민연결)의 정밀도를 낮게 잡는다 — 최악 가정이 보수적",
           "scenarios": {}}
    for name, prec in (("worst", lo), ("best", hi)):
        t = p_llm * prec
        fp = p_llm - t
        d = _min_effect(n, t, fp) if t > 0 else None
        out["scenarios"][name] = {"precision": round(prec, 3), "true_rate": round(t, 3), "min_relative_reduction": d}
    worst = out["scenarios"]["worst"]["min_relative_reduction"]
    out["downgrade"] = (worst is None) or worst > 0.5
    out["rule"] = "최악 정밀도 가정의 최소 상대 감소가 50%보다 크면(또는 100%로도 80%에 못 미치면) 방향성 확인 라운드로 격하"
    (OUT / "power.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "fit":
        asyncio.run(fit())
    elif cmd == "verify":
        asyncio.run(verify())
    else:
        power()
