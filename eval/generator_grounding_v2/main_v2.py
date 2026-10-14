"""
v2 본 실행 (4 ~ 7단계, 방향성 확인 라운드).

    python main_v2.py sample                 # 새 표본 70건(무작위, 시드 20261002) → result/main/inputs.jsonl
    python main_v2.py fitcache               # 70건 fit 캐시(gpt-5-mini minimal, 해시 기록) → result/main/fit_cache.jsonl
    python main_v2.py gen --cond v1          # v1 생성(purpose_prompt 가 v1 해시여야 함, fitter 없음)
    python main_v2.py gen --cond v2          # v2 생성(purpose_prompt v2 + 캐시 fitter, check_prompts_v2 통과 기록 필요)
    python main_v2.py gen --cond nofit       # v2-nofit 생성(purpose_prompt v2, fitter 없음)
    python main_v2.py measure --cond v1      # 검증기 v2 medium + 판정기 2회
    python main_v2.py latency                # 연결 모듈 지연(태스크 10 · 40개, fitter 유무)
"""

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

import sample_holdout as sh  # noqa: E402 — v1 표본 추출 · 스냅숏 조회(운영 경로)
from _common import load_personas, persona_info  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.nodes import _parse_message  # noqa: E402
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

MAIN = vc.RESULT / "main"
SEED = 20261002
N = 70
CHECK_V2 = vc.RESULT / "check_prompts_v2.json"


def base() -> dict:
    return json.loads(vc.BASELINE_V2.read_text(encoding="utf-8"))


def sample() -> None:
    out = MAIN / "inputs.jsonl"
    if out.exists():
        raise SystemExit(f"{out} 이 이미 있습니다")
    exclude = sh._original_products() | {r["product_id"] for r in vc.gg.load_inputs("holdout")}
    samples = sh.sample(N, SEED, exclude, "N")
    fetched = asyncio.run(sh._fetch([s["product_id"] for s in samples]))
    missing = [s["item_id"] for s in samples if s["product_id"] not in fetched]
    if missing:
        raise SystemExit(f"스냅숏 조회 실패: {missing}")
    personas = load_personas()
    rows = [{**s, "persona_info": persona_info(personas[s["persona_id"]]),
             "product_snapshot": json.loads(json.dumps(fetched[s["product_id"]], ensure_ascii=False))} for s in samples]
    MAIN.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, rows)
    print(f"표본 {len(rows)}건 · 목적 {dict((p, sum(r['purpose'] == p for r in rows)) for p in sorted({r['purpose'] for r in rows}))}")
    vc.gg.append_amendment("v2 본 표본", f"무작위 70건(시드 {SEED}, 원본 · 1라운드 보류 상품 {len(exclude)}개 제외)",
                           {"eval/generator_grounding_v2/result/main/inputs.jsonl": vc.gg.sha256(out)})


async def _fitcache() -> None:
    b = base()
    if vc.gg.sha256(vc.PERSONA_FIT) != b["persona_fit"] or vc.gg.sha256(vc.gg.PRODUCT_FIELDS) != b["product_fields"]:
        raise SystemExit("persona_fit.py · product_fields.py 가 잠금값과 다릅니다")
    items = load_jsonl(MAIN / "inputs.jsonl")
    fitter = pf.PersonaFitter()
    sem = asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            r = await fitter.fit(it["persona_info"], it["product_snapshot"])
            return {"item_id": it["item_id"], "persona_fit": b["persona_fit"], "product_fields": b["product_fields"],
                    **r.to_dict()}

    rows = await asyncio.gather(*(one(it) for it in items))
    write_jsonl(MAIN / "fit_cache.jsonl", rows)
    print(f"fit 캐시 {len(rows)}건 · ok {sum(r['status'] == 'ok' for r in rows)} · 위험 "
          f"{sum(bool(r['not_connectable'] or r['conflicts']) for r in rows)}")


class CachedFitter:
    """평가용 fitter — 캐시를 읽어 PersonaFitter.fit 과 같은 결과를 돌려준다(해시 대조)."""

    def __init__(self, by_snapshot: dict[str, pf.FitResult]):
        self._by = by_snapshot

    async def fit(self, persona_info_: dict, product_info: dict) -> pf.FitResult:
        return self._by[product_info.get("product_id")]


def _gen_guard(cond: str) -> str:
    b = base()
    now = vc.gg.sha256(vc.gg.PURPOSE_PROMPT)
    if cond == "v1" and now != b["purpose_prompt_v1"]:
        raise SystemExit("v1 인데 purpose_prompt.py 가 v1 해시가 아닙니다")
    if cond in ("v2", "nofit"):
        if now == b["purpose_prompt_v1"]:
            raise SystemExit(f"{cond} 인데 purpose_prompt.py 가 아직 v1 입니다")
        rec = json.loads(CHECK_V2.read_text(encoding="utf-8")) if CHECK_V2.exists() else {}
        if not (rec.get("passed") and rec.get("purpose_prompt") == now):
            raise SystemExit("현재 purpose_prompt.py 로 check_prompts_v2 를 통과한 기록이 없습니다")
    return now


async def _gen(cond: str) -> None:
    pp = _gen_guard(cond)
    items = load_jsonl(MAIN / "inputs.jsonl")
    fitter = None
    if cond == "v2":
        cache = load_jsonl(MAIN / "fit_cache.jsonl")
        b = base()
        if any(c["persona_fit"] != b["persona_fit"] or c["product_fields"] != b["product_fields"] for c in cache):
            raise SystemExit("fit 캐시의 해시가 잠금값과 다릅니다")
        pid = {it["item_id"]: it["product_snapshot"].get("product_id") for it in items}
        fitter = CachedFitter({pid[c["item_id"]]: pf.FitResult.from_dict(c) for c in cache})
    gen = CrmMessageGenerator(persona_fitter=fitter)
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    out_dir = MAIN / cond
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "messages.jsonl"
    done = {r["item_id"] for r in load_jsonl(out)} if out.exists() else set()
    lock = asyncio.Lock()

    async def one(it):
        tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
        tasks = await gen.get_brand_tone(tasks)
        tasks = await gen.get_crm_prompt(tasks, persona_info=it["persona_info"])
        prompt_text = "\n".join(m.content for m in tasks[0]["prompt"])
        g = await gen.generate_crm_message(tasks, llm)
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
               "fit_status": tasks[0].get("fit_status"),
               "generation": {"prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                              "purpose_prompt": pp, "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    todo = [it for it in items if it["item_id"] not in done]
    print(f"{cond}: 생성 {len(todo)}건(이미 {len(done)}건)", flush=True)
    await asyncio.gather(*(one(it) for it in todo))
    rows = {r["item_id"]: r for r in load_jsonl(out)}
    write_jsonl(out, [rows[it["item_id"]] for it in items if it["item_id"] in rows])
    print(f"→ {out} {len(rows)}/{len(items)} · fit_status {dict((s, sum(r.get('fit_status') == s for r in rows.values())) for s in ('ok', 'fallback', 'disabled'))}")


async def _measure(cond: str) -> None:
    import measure_v2 as mv
    b = base()
    await mv.run(mv.m1.load_messages(MAIN / cond / "messages.jsonl"), MAIN / cond, b["verifier_effort"], 2, False)


async def _latency() -> None:
    """get_crm_prompt 지연: fitter 있음(실시간 PersonaFitter) 대 없음, 태스크 10 · 40개(같은 페르소나 하나, 운영처럼)."""
    items = load_jsonl(MAIN / "inputs.jsonl")
    persona = items[0]["persona_info"]
    out = {}
    for n in (10, 40):
        tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"],
                  "brand_tone": "톤"} for it in items[:n]]
        res = {}
        for label, fitter in (("without", None), ("with", pf.PersonaFitter())):
            gen = CrmMessageGenerator(persona_fitter=fitter)
            times = []
            for _ in range(3 if n == 10 else 1):
                t0 = time.perf_counter()
                await gen.get_crm_prompt([dict(t) for t in tasks], persona_info=persona)
                times.append(time.perf_counter() - t0)
            res[label] = statistics.median(times)
        out[n] = res
    data = {"added_median_10_s": round(out[10]["with"] - out[10]["without"], 2),
            "throughput_ratio_40": None, "raw": out,
            "note": "get_crm_prompt 만 잰다(생성 호출 시간은 fitter 유무와 같으므로 비율은 생성 평균 시간을 더해 계산)"}
    # 처리량 비율: 생성 1회 평균 시간(1라운드 v1 생성 기록)을 더해 40개 전체 시간 비율로 근사
    lat = [r["generation"]["latency_s"] for r in load_jsonl(vc.gg.RESULT / "holdout" / "after" / "messages.jsonl")]
    gen_s = statistics.median(lat)
    data["generation_median_s"] = gen_s
    data["throughput_ratio_40"] = round((out[40]["with"] + gen_s) / (out[40]["without"] + gen_s), 2)
    (MAIN / "latency.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("sample", "fitcache", "gen", "measure", "latency"))
    ap.add_argument("--cond", choices=("v1", "v2", "nofit"))
    a = ap.parse_args()
    if a.cmd == "sample":
        sample()
    elif a.cmd == "fitcache":
        asyncio.run(_fitcache())
    elif a.cmd == "gen":
        asyncio.run(_gen(a.cond))
    elif a.cmd == "measure":
        asyncio.run(_measure(a.cond))
    else:
        asyncio.run(_latency())
