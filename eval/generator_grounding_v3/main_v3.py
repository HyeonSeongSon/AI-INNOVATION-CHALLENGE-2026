"""
v3 개발 라운드 실행 — 2라운드 새 표본 70건에 v3만 생성 · 측정하고 저장된 v1 · v2와 짝 비교한다(탐색적).

    python main_v3.py record --tag v3           # 생성 전: v3 해시 · 판정 규칙 · 반복 상한을 AMENDMENTS 에 기록
    python main_v3.py fitcache --tag v3         # 70건 fit(현재 persona_fit, 해시 기록) → result/dev/v3/fit_cache.jsonl
    python main_v3.py gen --tag v3              # v3 생성(캐시 fitter + 생성 후 검사, check_prompts_v3 통과 기록 필요)
    python main_v3.py rejudge --tag v3          # A단계: v1 · v2 · v3 210건을 같은 시점에 판정기 2회씩(feedback 저장)
    python main_v3.py verify --tag v3           # B단계: v3 검증기(medium) — A 통과 후에만
    python main_v3.py latency --tag v3          # 연결 모듈 지연(태스크 10 · 40개, 실시간 fitter 대 없음)
    python main_v3.py regression --tag v3       # 알려진 실패 8건 × v3 3회(규칙 검사)

반복(v3b, v3c …)은 같은 명령에 새 태그를 쓴다. 판정 · 보고는 compare_v3.py.
v3R(태그 v3r · v3r2): v2 대비 동시 판정(compare_v3.py v3r). 판정기 재판정은 시도별 경로 judge_<tag>/ 에 v1 · v2 · 태그를
같은 시점에 하고, 검증기는 A단계 기록 없이 바로 돈다. 재시도 태그는 1회차 v3r/fit_cache.jsonl 을 복사해 쓴다.
"""

import argparse
import asyncio
import hashlib
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone

import v3_common as v3
from v3_common import gg, vc
from gg_common import load_jsonl, write_jsonl

import main_v2 as m2  # noqa: E402 — CachedFitter
import measure_v3 as m3  # noqa: E402

DEV = v3.RESULT / "dev"
MAIN2 = vc.RESULT / "main"
CHECK_V3 = v3.RESULT / "check_prompts_v3.json"
EFFORT = "medium"


def items() -> list[dict]:
    return load_jsonl(MAIN2 / "inputs.jsonl")


def hashes_now() -> dict[str, str]:
    return {k: gg.sha256(p) for k, p in (("purpose_prompt", gg.PURPOSE_PROMPT), ("persona_fit", vc.PERSONA_FIT),
                                          ("product_fields", gg.PRODUCT_FIELDS), ("generate_crm_message", v3.GEN_CRM))}


def is_v3r(tag: str) -> bool:
    return tag.startswith("v3r")


V3R_RECORD = ("v3R 개발 {tag} 생성 전 기록(탐색적, 2라운드 새 표본 70건, 플랜 mellow-beaming-quiche 사용자 승인 2026-10-02). "
              "새 버전만 생성 · 측정하고 저장된 v2와 비교한다. 판정기는 v1 · v2 · {tag}를 judge_{tag}/ 에 같은 시점에 2회씩 재판정, "
              "검증기 v2 결과는 저장분. 동시 판정(모두 통과해야 함): 주 지표(특성어긋남 + 근거없는고민연결) ≤ 11(v2 7 + 이항 여유 4), "
              "9개 유형 합계 ≤ 16(v2 11 + 5), cta_clarity · personalization 은 v2 대비 점추정 상승이면서 짝 부트스트랩 단측 90% 하한 > −0.15, "
              "통과율 · tone · 목적 전달은 하한 > −0.15. v1 대비 품질 요건은 이번 게이트에서 제외(v1은 보고용). 고민 연결 0건 항목은 "
              "personalization 을 따로 보고하되 판정은 70건 전체. 재시도 1회까지: 근거 실패면 get_crm_prompt 연결별 GROUNDING_DEF 확인 필터"
              "(1회차 fit 캐시 재사용, 사람 확인 필수), 품질 실패면 연결 가능 상한 6 → 8, 연결 지시는 금지. 2회 안에 통과 없으면 최종 버전 = v1.")


def record(tag: str) -> None:
    rec = json.loads(CHECK_V3.read_text(encoding="utf-8")) if CHECK_V3.exists() else {}
    h = hashes_now()
    if not (rec.get("passed") and rec.get("purpose_prompt") == h["purpose_prompt"]):
        raise SystemExit("현재 purpose_prompt.py 로 check_prompts_v3 를 통과한 기록이 없습니다")
    content = V3R_RECORD.format(tag=tag) if is_v3r(tag) else (f"v3 개발 라운드 {tag} 생성 전 기록(탐색적, 2라운드 새 표본 70건). 판정: A단계(v1 · v2 · v3 동시 재판정, "
               "판정기 비열등 v1 대비 통과율 −0.15 · personalization · cta_clarity · tone −0.3, 형식 위반 +2, CTA ≥95%, "
               "정리 정규식 각 v2+1 이내) → B단계(주 지표 v3 ≤ v2+2, 8개 유형 v1+1, 목적 전달 −0.15, 지연 +5초 · 1.5배). "
               "반복 상한 A 재시도 2 · B 재시도 1, 통과 버전이 없으면 최종 버전 = v1. "
               "플랜 변경(사용자 결정 2026-10-02): 3건 시험에서 N034 고민 연결 무관 근거가 재발해 concern 에만 어휘 겹침 "
               "규칙 추가(사람 판정 116건 중 고민 44건: 무관 1/1 잡음 · 관련 3/43 내림), 내린 항목은 생성 후 검사 금지어에서 제외.")
    gg.append_amendment(f"v3 개발 기록({tag})", content, {
        "backend/app/agents/generate_message_agent/prompts/purpose_prompt.py": h["purpose_prompt"],
        "backend/app/agents/generate_message_agent/prompts/persona_fit.py": h["persona_fit"],
        "backend/app/agents/generate_message_agent/prompts/product_fields.py": h["product_fields"],
        "backend/app/agents/generate_message_agent/services/generate_crm_message.py": h["generate_crm_message"]})
    print("기록함:", h)


def _recorded(tag: str) -> dict[str, str]:
    es = [e for e in gg.amendments_entries() if e["kind"] == f"v3 개발 기록({tag})"]
    if not es:
        raise SystemExit(f"AMENDMENTS 에 'v3 개발 기록({tag})' 이 없습니다 — record 를 먼저 한다")
    nh = es[-1]["new_hashes"]
    return {k.split("/")[-1].removesuffix(".py"): v for k, v in nh.items()}


def guard(tag: str) -> None:
    now, rec = hashes_now(), _recorded(tag)
    bad = [k for k in now if rec.get(k) != now[k]]
    if bad:
        raise SystemExit(f"기록({tag})과 다른 파일: {bad}")


async def _fitcache(tag: str) -> None:
    guard(tag)
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    fitter, h = pf.PersonaFitter(), hashes_now()
    sem = asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            r = await fitter.fit(it["persona_info"], it["product_snapshot"])
        return {"item_id": it["item_id"], "persona_fit": h["persona_fit"], "product_fields": h["product_fields"], **r.to_dict()}

    rows = await asyncio.gather(*(one(it) for it in items()))
    (DEV / tag).mkdir(parents=True, exist_ok=True)
    write_jsonl(DEV / tag / "fit_cache.jsonl", rows)
    n = len(rows)
    print(f"fit {n}건 · ok {sum(r['status'] == 'ok' for r in rows)} · 연결 가능 평균 {sum(len(r['connectable']) for r in rows) / n:.1f}"
          f" · 내림 {sum(len(r['demoted']) for r in rows)}(어휘 {sum(len(r['lexical_demoted']) for r in rows)} · 모순 "
          f"{sum(1 for r in rows for d in r['demoted'] if '모순' in d['reason'])})")


async def _gen(tag: str) -> None:
    guard(tag)
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.nodes import _parse_message
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    its = items()
    cache = load_jsonl(DEV / tag / "fit_cache.jsonl")
    h = hashes_now()
    if any(c["persona_fit"] != h["persona_fit"] or c["product_fields"] != h["product_fields"] for c in cache):
        raise SystemExit("fit 캐시 해시가 현재 파일과 다릅니다 — fitcache 를 다시 돌린다")
    pid = {it["item_id"]: it["product_snapshot"].get("product_id") for it in its}
    gen = CrmMessageGenerator(persona_fitter=m2.CachedFitter({pid[c["item_id"]]: pf.FitResult.from_dict(c) for c in cache}))
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    out = DEV / tag / "messages.jsonl"
    done = {r["item_id"] for r in load_jsonl(out)} if out.exists() else set()
    lock, sem = asyncio.Lock(), asyncio.Semaphore(8)

    async def one(it):
        async with sem:
            t0 = time.perf_counter()
            tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
            tasks = await gen.get_brand_tone(tasks)
            tasks = await gen.get_crm_prompt(tasks, persona_info=it["persona_info"])
            prompt_text = "\n".join(m.content for m in tasks[0]["prompt"])
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
        row = {**it, "tag": tag, "title": msg.get("title", ""), "message": msg.get("message", ""), "json_ok": ok,
               "fit_status": g[0].get("fit_status"), "fit_recheck": g[0].get("fit_recheck"),
               "generation": {"prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                              "purpose_prompt": h["purpose_prompt"], "latency_s": dt,
                              "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    todo = [it for it in its if it["item_id"] not in done]
    print(f"{tag}: 생성 {len(todo)}건(이미 {len(done)}건)", flush=True)
    await asyncio.gather(*(one(it) for it in todo))
    rows = {r["item_id"]: r for r in load_jsonl(out)}
    write_jsonl(out, [rows[it["item_id"]] for it in its if it["item_id"] in rows])
    rc = [r.get("fit_recheck") for r in rows.values()]
    print(f"→ {out} {len(rows)}/{len(its)} · JSON {sum(r['json_ok'] for r in rows.values())} · fit_recheck "
          f"{dict((s, rc.count(s)) for s in ('none', 'regenerated', 'still_hit'))}")


def messages(tag: str) -> list[dict]:
    p = (MAIN2 / tag / "messages.jsonl") if tag in ("v1", "v2") else (DEV / tag / "messages.jsonl")
    return load_jsonl(p)


def judge_dir(tag: str):
    """v3R 은 시도마다 새 경로(rejudge 가 이미 있는 판정을 건너뛰므로, 같은 시점 판정을 지키려면 경로를 나눈다)."""
    return DEV / f"judge_{tag}" if is_v3r(tag) else DEV / "judge"


async def _rejudge(tag: str) -> None:
    for t in ("v1", "v2", tag):
        ms = messages(t)
        await m3.rejudge(ms, judge_dir(tag) / f"{t}.jsonl", 2)


async def _verify(tag: str) -> None:
    import measure_v2 as mv
    import measure as m1
    a = DEV / tag / "stageA.json"
    if not is_v3r(tag) and not (a.exists() and json.loads(a.read_text(encoding="utf-8")).get("passed")):
        raise SystemExit("A단계 통과 기록이 없습니다(compare_v3.py stageA)")
    await mv.run(m1.load_messages(DEV / tag / "messages.jsonl"), DEV / tag, EFFORT, 0, False)


async def _latency(tag: str) -> None:
    """main_v2._latency 와 같은 방식(get_crm_prompt 지연 · 처리량 근사). 생성 후 검사는 v3R 에서 지웠다."""
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    its = items()
    persona = its[0]["persona_info"]
    out = {}
    for n in (10, 40):
        tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"],
                  "brand_tone": "톤"} for it in its[:n]]
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
    lat = [r["generation"]["latency_s"] for r in load_jsonl(vc.gg.RESULT / "holdout" / "after" / "messages.jsonl")]
    gen_s = statistics.median(lat)
    data = {"added_median_10_s": round(out[10]["with"] - out[10]["without"], 2),
            "throughput_ratio_40": round((out[40]["with"] + gen_s) / (out[40]["without"] + gen_s), 2),
            "generation_median_s": gen_s, "raw": out,
            "note": "get_crm_prompt 지연은 main_v2 와 같은 방식(현재 persona_fit 프롬프트로 실측)."}
    (DEV / tag / "latency.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "raw"}, ensure_ascii=False, indent=2))


async def _regression(tag: str) -> None:
    guard(tag)
    import regression_v2 as rg
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.core.data_loader import get_brand_tones
    from app.agents.generate_message_agent.nodes import _parse_message
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    src = {s: {r["item_id"]: r for r in vc.gg.load_inputs(s)} for s in ("holdout", "insample")}
    gen = CrmMessageGenerator(persona_fitter=pf.PersonaFitter())
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    tones = get_brand_tones().get("brand_ton_prompt", {})
    sem = asyncio.Semaphore(8)

    async def one(iid, rep):
        it = src[rg.CASES[iid][0]][iid]
        async with sem:
            tasks = [{"product_id": it.get("product_id") or it["product_snapshot"].get("product_id"),
                      "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
            tasks = await gen.get_brand_tone(tasks)
            tasks = await gen.get_crm_prompt(tasks, persona_info=it["persona_info"])
            g = await gen.generate_crm_message(tasks, llm)
        m = _parse_message(g[0]["message"]) if g else {"title": "", "message": ""}
        row = {**it, "item_id": f"{iid}#{tag}#{rep}", "case": iid, "cond": tag, "rep": rep, "title": m.get("title", ""),
               "message": m.get("message", ""), "fit_recheck": g[0].get("fit_recheck") if g else None}
        row["known_failure_hit"] = re.findall(rg.CASES[iid][2], row["title"] + " " + row["message"])
        reg = m3.regex_metrics_v3(row, str(tones.get(it["brand"], "") or ""))
        row["cleanup"] = {k: reg[k] for k in m3.CLEANUP}
        return row

    rows = await asyncio.gather(*(one(i, r) for i in rg.CASES for r in range(1, rg.REPS + 1)))
    write_jsonl(DEV / tag / "regression.jsonl", rows)
    prev = load_jsonl(vc.RESULT / "regression" / "messages.jsonl")
    L = [f"# 회귀 시험 — 알려진 실패 8건 × {tag} {rg.REPS}회 (규칙 검사, v1 · v2는 2라운드 저장분)", "",
         f"| 항목 | 알려진 실패 | v1 | v2 | {tag} |", "|---|---|---|---|---|"]
    for iid, (_, desc, _p) in rg.CASES.items():
        c = {k: sum(1 for r in prev if r["case"] == iid and r["cond"] == k and r["known_failure_hit"]) for k in ("v1", "v2")}
        c3 = sum(1 for r in rows if r["case"] == iid and r["known_failure_hit"])
        L.append(f"| {iid} | {desc} | {c['v1']}/{rg.REPS} | {c['v2']}/{rg.REPS} | {c3}/{rg.REPS} |")
    L += ["", "재발 후보는 문구 일치만 본 것이다. 아래 문장을 훑어 실제 재발인지 본다.", ""]
    for r in sorted(rows, key=lambda x: (x["case"], x["rep"])):
        if r["known_failure_hit"]:
            sents = [s for s in re.split(r"(?<=[.!?])\s+|\n", r["title"] + " / " + r["message"]) if re.search(rg.CASES[r["case"]][2], s)]
            L.append(f"- **{r['case']} #{r['rep']}**: " + " … ".join(sents)[:300])
    (DEV / tag / "regression.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("record", "fitcache", "gen", "rejudge", "verify", "latency", "regression"))
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    if a.cmd == "record":
        record(a.tag)
    else:
        asyncio.run({"fitcache": _fitcache, "gen": _gen, "rejudge": _rejudge, "verify": _verify,
                     "latency": _latency, "regression": _regression}[a.cmd](a.tag))


if __name__ == "__main__":
    main()
