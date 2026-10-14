"""
V4 단계 2 — 개발 시험(N + F 140건). V4 만 새로 생성 · 측정하고 저장된 v3R 과 비교한다.

    python main_v4.py record --tag v4     # 생성 전 기록(최종 버전 파일 5개 해시가 단계 1 결과 기록과 같은지 대조)
    python main_v4.py gen --tag v4        # 생성(단계 1 fit 캐시 + 실제 생성기: 점검 A · 1회 재생성 포함)
    python main_v4.py verify --tag v4     # 검증기(gpt-5.5 medium, measure_v2 그대로)
    python main_v4.py rejudge --tag v4    # 판정기: v3R 과 V4 를 같은 시점에 2회씩 → result/dev/judge_<tag>/
    python main_v4.py latency --tag v4    # 5태스크 배치 끝까지(fit + 연결 확인 + 생성 + 재생성) 지연, 6배치(보고용)

판정은 compare_v4.py, 근거 있는 개인화 · 짝 층은 metrics_v4.py, 게이트 뒤 재작성 점검은 rewrite_check_v4.py.
재시도 태그(v4r)는 AMENDMENTS 에 재시도 내용을 먼저 기록한 뒤 같은 명령으로 돈다.
"""

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone

import v4_common as c

DEV = c.RESULT / "dev"
STAGE1_RESULT_KIND = "V4 단계 1 결과"
INPUT_KEYS = ("item_id", "persona_id", "product_id", "brand", "category", "tag", "sub_tag", "purpose", "persona_use",
              "persona_info", "product_snapshot")
EFFORT = "medium"


def final_files():
    from fit_check_v4 import FINAL_FILES, REL
    return {REL(p): c.gg.sha256(p) for p in FINAL_FILES}


def items() -> list[dict]:
    """N 70 + F 70 입력(저장된 v3R 메시지에서 입력 필드만)."""
    out = []
    for key in ("v3r_N", "v3r_F"):
        msgs, _ = c.stored(key)
        out += [{k: m[k] for k in INPUT_KEYS if k in m} for m in msgs.values()]
    pids = [it["product_snapshot"].get("product_id") for it in out]
    if len(set(pids)) != len(pids):
        raise SystemExit("상품 ID 가 겹칩니다(fit 캐시 키 충돌)")
    return out


def v3r_messages() -> list[dict]:
    out = []
    for key in ("v3r_N", "v3r_F"):
        msgs, _ = c.stored(key)
        out += list(msgs.values())
    return out


def tag_messages(tag: str) -> list[dict]:
    return c.load_jsonl(DEV / tag / "messages.jsonl")


def judge_dir(tag: str):
    return DEV / f"judge_{tag}"


def _record_kind(tag: str) -> str:
    return f"V4 개발 생성 전 기록({tag})"


def record(tag: str) -> None:
    if any(e["kind"] == _record_kind(tag) for e in c.gg.amendments_entries()):
        raise SystemExit("이미 기록됨")
    now = final_files()
    base = next((e for e in reversed(c.gg.amendments_entries()) if e["kind"] == STAGE1_RESULT_KIND), None)
    if base is None:
        raise SystemExit("단계 1 결과 기록이 없습니다")
    diff = [k for k, v in now.items() if base["new_hashes"].get(k) != v]
    if diff and tag == "v4":
        raise SystemExit(f"단계 1 결과 기록과 다른 최종 버전 파일: {diff}")
    chk = json.loads((c.RESULT / "check_prompts_v4.json").read_text(encoding="utf-8"))
    if chk.get("fails"):
        raise SystemExit("check_prompts_v4 실패가 있습니다")
    content = (f"V4 개발 {tag} 생성 전 기록(결과 보기 전). 표본 N + F 140건, fit 은 단계 1 캐시(result/stage1/fit_cache.jsonl), "
               "생성은 운영 생성기(get_crm_prompt + generate_crm_message: 거른 페르소나 · 승인 연결만 · 점검 A · 1회 재생성). "
               "판정 규칙은 AMENDMENTS 'V4 사전 기록(단계 0)' 그대로(개인화는 비열등만, 검증기는 v3R 저장분). "
               f"check_prompts_v4 {chk['prompts']}개 통과." + (f" 단계 1 대비 바뀐 파일: {diff}" if diff else ""))
    e = c.gg.append_amendment(_record_kind(tag), content, now)
    print(f"AMENDMENTS {e['id']} 기록({tag})")


def guard(tag: str) -> dict:
    rec = next((e for e in reversed(c.gg.amendments_entries()) if e["kind"] == _record_kind(tag)), None)
    if rec is None:
        raise SystemExit(f"생성 전 기록이 먼저다: python main_v4.py record --tag {tag}")
    now = final_files()
    diff = [k for k, v in now.items() if rec["new_hashes"].get(k) != v]
    if diff:
        raise SystemExit(f"생성 전 기록과 다른 파일: {diff}")
    return now


async def _gen(tag: str) -> None:
    h = guard(tag)
    import main_v2 as m2  # CachedFitter
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    from app.agents.generate_message_agent.services import claim_check as cc
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    its = items()
    cache = c.load_jsonl(c.RESULT / "stage1" / "fit_cache.jsonl")
    if any(r.get("persona_fit") != c.gg.sha256(c.gg.REPO / "backend/app/agents/generate_message_agent/prompts/persona_fit.py")
           for r in cache):
        raise SystemExit("fit 캐시 해시가 현재 persona_fit.py 와 다릅니다")
    pid = {it["item_id"]: it["product_snapshot"].get("product_id") for it in its}
    gen = CrmMessageGenerator(persona_fitter=m2.CachedFitter({pid[r["item_id"]]: pf.FitResult.from_dict(r) for r in cache}))
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    out = DEV / tag / "messages.jsonl"
    done = {r["item_id"] for r in c.load_jsonl(out)} if out.exists() else set()
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
        msg = cc.parse_message(raw)
        try:
            ok = isinstance(json.loads(content), dict)
        except Exception:  # noqa: BLE001
            ok = False
        row = {**it, "tag": tag, "title": msg["title"], "message": msg["message"], "json_ok": ok,
               "fit_status": g[0].get("fit_status"), "claim_check": g[0].get("claim_check"),
               "claim_hits": [{k: x[k] for k in ("cat", "sub", "text", "where")} for x in g[0].get("claim_hits", [])],
               "claim_hits_after": [{k: x[k] for k in ("cat", "sub", "text", "where")} for x in g[0].get("claim_hits_after", [])],
               "generation": {"prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(), "files": h,
                              "latency_s": dt, "model": settings.chatgpt_model_name,
                              "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    todo = [it for it in its if it["item_id"] not in done]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"{tag}: 생성 {len(todo)}건(이미 {len(done)}건)", flush=True)
    await asyncio.gather(*(one(it) for it in todo))
    rows = {r["item_id"]: r for r in c.load_jsonl(out)}
    c.write_jsonl(out, [rows[it["item_id"]] for it in its if it["item_id"] in rows])
    st = [r.get("claim_check") for r in rows.values()]
    print(f"→ {out} {len(rows)}/{len(its)} · JSON {sum(r['json_ok'] for r in rows.values())} · 점검 "
          f"{dict((s, st.count(s)) for s in ('none', 'regenerated', 'still_hit', 'error', 'off'))}")


async def _verify(tag: str) -> None:
    guard(tag)
    import measure as m1
    import measure_v2 as mv
    await mv.run(m1.load_messages(DEV / tag / "messages.jsonl"), DEV / tag, EFFORT, 0, False)


async def _rejudge(tag: str) -> None:
    import measure_v3 as m3
    await m3.rejudge(v3r_messages(), judge_dir(tag) / "v3r.jsonl", 2)
    await m3.rejudge(tag_messages(tag), judge_dir(tag) / f"{tag}.jsonl", 2)


async def _latency(tag: str) -> None:
    """운영 경로 그대로(실제 fitter + 연결 확인 + 생성 + 점검 · 재생성), 같은 페르소나 5태스크 배치 6회(보고용)."""
    guard(tag)
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.prompts import persona_fit as pf
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    its = items()[:30]
    gen = CrmMessageGenerator(persona_fitter=pf.PersonaFitter())
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    batches, regen = [], 0
    for b in range(6):
        group = its[b * 5:(b + 1) * 5]
        persona = group[0]["persona_info"]
        t0 = time.perf_counter()
        tasks = [{"product_id": it["product_id"], "purpose": it["purpose"], "product_info": it["product_snapshot"]} for it in group]
        tasks = await gen.get_brand_tone(tasks)
        tasks = await gen.get_crm_prompt(tasks, persona_info=persona)
        g = await gen.generate_crm_message(tasks, llm)
        batches.append(round(time.perf_counter() - t0, 2))
        regen += sum(1 for x in g if x.get("claim_check") in ("regenerated", "still_hit"))
    srt = sorted(batches)
    data = {"batch5_median_s": round(statistics.median(batches), 2), "batch5_p90_s": srt[int(0.9 * (len(srt) - 1) + 0.5)],
            "batches_s": batches, "regenerated_tasks": regen, "tasks": 30,
            "note": "운영 경로 끝까지(품질 게이트 · 재작성 제외), 보고용"}
    (DEV / tag / "latency.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(data)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("record", "gen", "verify", "rejudge", "latency"))
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    if a.cmd == "record":
        record(a.tag)
    else:
        asyncio.run({"gen": _gen, "verify": _verify, "rejudge": _rejudge, "latency": _latency}[a.cmd](a.tag))


if __name__ == "__main__":
    main()
