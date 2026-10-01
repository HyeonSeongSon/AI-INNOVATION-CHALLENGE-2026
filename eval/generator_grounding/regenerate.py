"""
수정 전 · 후 메시지 생성 (3 · 5단계) — 같은 입력을 생성기의 실제 경로로 다시 생성한다.

    python regenerate.py --set holdout --tag before
    python regenerate.py --set insample --tag after

- 저장된 스냅숏을 product_info 로 넣고 CrmMessageGenerator 의 get_brand_tone → get_crm_prompt →
  generate_crm_message 를 탄다(DB 조회 없음). 응답 해석은 nodes._parse_message 를 그대로 쓴다.
- 해시 가드
  - before: purpose_prompt.py 해시가 baseline_hashes.json 의 기준과 같아야 한다.
  - after: 기준과 달라야 하고, 현재 해시로 check_prompts.py 를 통과한 기록(result/check_prompts.json)이 있어야 한다.
- 이어 하기: messages.jsonl 에 이미 있는 item_id 는 건너뛴다(크레딧 소진 등으로 끊겼을 때).
  regen_meta.json 의 generated_from(첫 생성 시각)은 이어 해도 바뀌지 않는다.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone

import gg_common as gg
from gg_common import load_jsonl

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.nodes import _parse_message  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

CHECK_PROMPTS = gg.RESULT / "check_prompts.json"


def guard(tag: str) -> str:
    base = gg.load_baseline()["purpose_prompt"]
    now = gg.sha256(gg.PURPOSE_PROMPT)
    if tag == "before" and now != base:
        raise SystemExit(f"before 인데 purpose_prompt.py 해시가 기준과 다릅니다({now[:12]} ≠ {base[:12]})")
    if tag == "after":
        if now == base:
            raise SystemExit("after 인데 purpose_prompt.py 가 기준과 같습니다(수정 전)")
        rec = json.loads(CHECK_PROMPTS.read_text(encoding="utf-8")) if CHECK_PROMPTS.exists() else {}
        if not (rec.get("passed") and rec.get("purpose_prompt") == now):
            raise SystemExit("현재 purpose_prompt.py 로 check_prompts.py 를 통과한 기록이 없습니다")
    return now


def _json_ok(content: str) -> bool:
    try:
        parsed = json.loads(content)
        return isinstance(parsed, dict) and "title" in parsed
    except Exception:
        return False


async def generate(items: list[dict], out_path, tag: str) -> list[str]:
    generator = CrmMessageGenerator()
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    lock = asyncio.Lock()
    failed: list[str] = []

    async def one(it: dict) -> None:
        tasks = [{"product_id": it.get("product_id") or it["product_snapshot"].get("product_id"), "purpose": it["purpose"],
                  "product_info": it["product_snapshot"]}]
        tasks = await generator.get_brand_tone(tasks)
        if not tasks:
            failed.append(it["item_id"])
            return
        tasks = await generator.get_crm_prompt(tasks, persona_info=it["persona_info"])
        prompt_text = "\n".join(m.content for m in tasks[0]["prompt"])
        t0 = time.perf_counter()
        generated = await generator.generate_crm_message(tasks, llm)
        latency = round(time.perf_counter() - t0, 2)
        if not generated:
            failed.append(it["item_id"])
            return
        raw = generated[0]["message"]
        content = raw.content if hasattr(raw, "content") else str(raw)
        msg = _parse_message(raw)
        row = {**it, "tag": tag, "title": msg.get("title", ""), "message": msg.get("message", ""),
               "json_ok": _json_ok(content),
               "generation": {"model": settings.chatgpt_model_name,
                              "temperature_setting": settings.llm_temperature_generator,
                              "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                              "latency_s": latency, "generated_at": datetime.now(timezone.utc).isoformat()}}
        async with lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    await asyncio.gather(*(one(it) for it in items))
    return failed


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=gg.SETS)
    ap.add_argument("--tag", required=True, choices=("before", "after"))
    a = ap.parse_args()

    pp_hash = guard(a.tag)
    inputs = gg.load_inputs(a.set)
    out_dir = gg.set_dir(a.set) / a.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "messages.jsonl"
    meta_path = out_dir / "regen_meta.json"
    done = {r["item_id"] for r in load_jsonl(out_path)} if out_path.exists() else set()
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if meta and meta.get("purpose_prompt") != pp_hash:
        raise SystemExit("이어 하려는 결과와 purpose_prompt.py 해시가 다릅니다(섞이지 않게 중단)")
    todo = [it for it in inputs if it["item_id"] not in done]
    print(f"{a.set}/{a.tag}: 입력 {len(inputs)}건 · 이미 생성 {len(done)}건 · 이번 생성 {len(todo)}건")
    started = datetime.now(timezone.utc).isoformat()
    failed = asyncio.run(generate(todo, out_path, a.tag)) if todo else []

    # 입력 순서대로 다시 정렬해 저장한다
    rows = {r["item_id"]: r for r in load_jsonl(out_path)} if out_path.exists() else {}
    order = [it["item_id"] for it in inputs]
    gg.write_jsonl(out_path, [rows[i] for i in order if i in rows])
    meta = {
        "set": a.set, "tag": a.tag,
        "generated_from": meta.get("generated_from") or started,
        "generated_to": datetime.now(timezone.utc).isoformat(),
        "n_inputs": len(inputs), "n_generated": len(rows),
        "missing": [i for i in order if i not in rows], "failed_this_run": failed,
        "purpose_prompt": pp_hash,
        "product_fields": gg.sha256(gg.PRODUCT_FIELDS) if gg.PRODUCT_FIELDS.exists() else None,
        "gate_files": gg.file_hashes(gg.GATE_FILES),
        "model": settings.chatgpt_model_name, "temperature_setting": settings.llm_temperature_generator,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"생성 {len(rows)}/{len(inputs)} · 이번 실패 {len(failed)} → {out_path}")
    if meta["missing"]:
        print(f"빠진 항목: {meta['missing']} — 다시 돌리면 이어서 생성합니다")


if __name__ == "__main__":
    main()
