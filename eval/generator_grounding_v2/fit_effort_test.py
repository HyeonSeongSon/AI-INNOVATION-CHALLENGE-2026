"""
fit effort 시험 (2단계, 잠금 전) — minimal · low 별로 지연과 '지어낸 근거 비율'을 같이 잰다.

    python fit_effort_test.py

- 대상: 1라운드 보류 v1 입력 70건 중 시드 20261007로 20쌍(같은 20쌍을 두 effort 에 씀)
- 지연: 단건 호출 지연 중앙값 + 10쌍 동시 호출의 전체 시간(태스크 10개 기준 추가 지연 추정)
- 지어낸 근거 비율 = 코드 검증에서 내려간 connectable 수 / LLM 이 낸 connectable 수 (분모는 항목 수)
- 선택 규칙(PREREG_v2): 지연 상한(+3초)을 지키는 effort 중, minimal 비율이 low 보다 5%p 이상 높지 않으면 minimal.
  둘 다 20%를 넘으면 fit 프롬프트를 고친다.
결과: result/fit_effort/{effort}.jsonl (20쌍 fit 원본 — 3.1 무관 근거 확인에 그대로 씀), summary.json
"""

import asyncio
import json
import random
import statistics
import sys
import time

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402

OUT = vc.RESULT / "fit_effort"
SEED = 20261007
LATENCY_CAP_S = 3.0


async def one(fitter: pf.PersonaFitter, it: dict) -> dict:
    """PersonaFitter.fit 과 같은 호출이지만 검증 전 원본 수와 지연을 함께 남긴다."""
    user = ("[페르소나]\n" + pf._persona_text(it["persona_info"]) + "\n\n[상품정보]\n"
            + json.dumps(pf.generation_product_info(it["product_snapshot"]), ensure_ascii=False, indent=1))
    t0 = time.perf_counter()
    try:
        raw = await fitter._structured.ainvoke([("system", pf.SYSTEM), ("human", user)])
        lat = time.perf_counter() - t0
        res = pf.verify(raw, it["product_snapshot"])
        return {"item_id": it["item_id"], "latency_s": round(lat, 2), "raw_connectable": len(raw.connectable),
                "demoted_connectable": sum(1 for d in res.demoted if "need_type" in d), "fit": res.to_dict()}
    except Exception as e:  # noqa: BLE001
        return {"item_id": it["item_id"], "latency_s": round(time.perf_counter() - t0, 2), "error": f"{type(e).__name__}: {e}"[:300]}


async def main() -> None:
    items = load_jsonl(vc.gg.RESULT / "holdout" / "inputs.jsonl")
    pick = random.Random(SEED).sample(items, 20)
    OUT.mkdir(exist_ok=True)
    model = settings.persona_fit_model_name or settings.chatgpt_model_name
    summary = {}
    for effort in ("minimal", "low"):
        fitter = pf.PersonaFitter(llm=get_llm(model, reasoning_effort=effort))
        sem = asyncio.Semaphore(5)

        async def guarded(it):
            async with sem:
                return await one(fitter, it)

        rows = await asyncio.gather(*(guarded(it) for it in pick))
        t0 = time.perf_counter()
        await asyncio.gather(*(one(fitter, it) for it in pick[:10]))  # 태스크 10개 동시(운영처럼)
        batch10 = time.perf_counter() - t0
        write_jsonl(OUT / f"{effort}.jsonl", rows)
        ok = [r for r in rows if "error" not in r]
        raw_n = sum(r["raw_connectable"] for r in ok)
        dem = sum(r["demoted_connectable"] for r in ok)
        summary[effort] = {"n_ok": len(ok), "errors": len(rows) - len(ok),
                           "latency_median_s": round(statistics.median(r["latency_s"] for r in ok), 2) if ok else None,
                           "batch10_wall_s": round(batch10, 2),
                           "connectable_raw": raw_n, "connectable_demoted": dem,
                           "fabricated_rate": round(dem / raw_n, 3) if raw_n else None,
                           "risky_pairs": sum(1 for r in ok if r["fit"]["not_connectable"] or r["fit"]["conflicts"])}
        print(effort, summary[effort], flush=True)
    mn, lo = summary["minimal"], summary["low"]
    within = {e: (s["batch10_wall_s"] is not None and s["batch10_wall_s"] <= LATENCY_CAP_S) for e, s in summary.items()}
    if (mn["fabricated_rate"] or 0) > 0.2 and (lo["fabricated_rate"] or 0) > 0.2:
        choice = "프롬프트 수정 필요(두 effort 모두 지어낸 근거 20% 초과)"
    elif within["minimal"] and (mn["fabricated_rate"] or 0) - (lo["fabricated_rate"] or 0) < 0.05:
        choice = "minimal"
    elif within["low"]:
        choice = "low"
    else:
        choice = "지연 상한 초과 — 프롬프트 축소 후 재시험 필요"
    summary["choice"] = choice
    summary["latency_cap_s"] = LATENCY_CAP_S
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("선택:", choice)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
