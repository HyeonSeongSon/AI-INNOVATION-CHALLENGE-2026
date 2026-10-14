"""
V4 단계 2 보고용 — 운영의 품질 게이트 → 피드백 재작성 경로를 V4 개발 메시지에 그대로 돌린다(측정 범위 밖 경로 점검).

    python rewrite_check_v4.py probe --tag v4   # 선결 조건: OpenSearch 의미 유사도 API 가 응답하는지
    python rewrite_check_v4.py run --tag v4     # 게이트(규칙 → 의미 유사도 → 판정기) · 실패 시 재작성(최대 2회, nodes._MAX_RETRIES)
    python rewrite_check_v4.py verify --tag v4  # 재작성된 메시지에만 검증기 → 재작성 전후 근거 없는 주장 비교 → rewrite_check.md

- 운영 코드(quality_check.py · apply_feedback.py · apply_feedback_prompt.py · nodes.py)는 import 만 한다(잠금 파일).
  DB 조회만 평가 스냅숏으로 바꾼다(상품 클라이언트 대역). 페르소나는 운영과 같이 원본 전체를 넘긴다.
- 의미 유사도는 로컬 OpenSearch 인덱스 기준이다(운영 인덱스와 다를 수 있음 — 보고서에 적는다).
"""

import argparse
import asyncio
import json
import sys

import v4_common as c
import main_v4 as mv4


class SnapshotProductClient:
    """품질 게이트 · 재작성의 DB 조회를 평가 스냅숏으로 대신한다."""

    def __init__(self, by_id: dict[str, dict]):
        self._by = by_id

    async def get_products_detail_from_db(self, ids):
        return [self._by[i] for i in ids if i in self._by]

    def flatten_product_data(self, p):
        return p

    async def get_merged_product_info(self, pid):
        return self._by.get(pid, {})


def out_dir(tag: str):
    return mv4.DEV / tag / "rewrite"


async def _probe(tag: str) -> bool:
    """운영 게이트의 의미 유사도 호출을 그대로 한 번 해 본다(요청 형식을 추측하지 않는다)."""
    from app.agents.generate_message_agent.services.quality_check import QualityChecker
    checker = QualityChecker()
    try:
        passed, res = await checker._run_semantic_similarity_check("촉촉한 보습 크림", "세안 후 바르는 데일리 크림입니다.")
    finally:
        await checker.aclose()
    ok = not (res and res[0].get("error") == "api_unavailable")
    print(f"의미 유사도 API {'응답' if ok else '응답 없음(api_unavailable)'} · 시험 문장 통과={passed}")
    return ok


async def _run(tag: str) -> None:
    if not await _probe(tag):
        raise SystemExit("OpenSearch 의미 유사도 API 가 응답하지 않습니다 — 켜고 다시 실행")
    from app.config.settings import settings
    from app.core.llm_factory import get_llm
    from app.agents.generate_message_agent.nodes import _MAX_RETRIES
    from app.agents.generate_message_agent.services.apply_feedback import ApplyFeedback
    from app.agents.generate_message_agent.services.quality_check import QualityChecker
    msgs = mv4.tag_messages(tag)
    by_id = {m["product_id"]: m["product_snapshot"] for m in msgs}
    checker, applier = QualityChecker(), ApplyFeedback()
    checker._product_client = SnapshotProductClient(by_id)
    applier._product_client = SnapshotProductClient(by_id)
    judge_llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier, reasoning_effort="low")
    fb_llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_creative)
    sem = asyncio.Semaphore(6)

    async def one(m):
        task = {"product_id": m["product_id"], "purpose": m["purpose"], "brand": m["brand"],
                "message": {"title": m["title"], "message": m["message"]}}
        rounds = []
        async with sem:
            for retry in range(_MAX_RETRIES + 1):
                qc = await checker.check_quality(message=task["message"], product_id=m["product_id"], purpose=m["purpose"],
                                                 llm=judge_llm, persona_info=m["persona_info"])
                rounds.append({"message": task["message"], "passed": qc["passed"], "failed_stage": qc.get("failed_stage"),
                               "failure_reason": qc.get("failure_reason")})
                if qc["passed"] or retry == _MAX_RETRIES:
                    break
                task = await applier.apply_feedback({**task, "quality_check": qc}, fb_llm, persona_info=m["persona_info"])
        return {"item_id": m["item_id"], "rounds": rounds, "rewritten": len(rounds) > 1,
                "final": task["message"], "final_passed": rounds[-1]["passed"]}

    rows = await asyncio.gather(*(one(m) for m in msgs))
    od = out_dir(tag)
    c.write_jsonl(od / "rounds.jsonl", rows)
    re_msgs = [{**m, "item_id": m["item_id"], "title": r["final"]["title"], "message": r["final"]["message"]}
               for m, r in zip(msgs, rows) if r["rewritten"]]
    c.write_jsonl(od / "messages.jsonl", re_msgs)
    stages = {}
    for r in rows:
        s = r["rounds"][0]["failed_stage"] or "통과"
        stages[s] = stages.get(s, 0) + 1
    print(f"게이트 첫 판정 {stages} · 재작성 {len(re_msgs)}건 · 최종 불통과 {sum(not r['final_passed'] for r in rows)}건")


async def _verify(tag: str) -> None:
    import measure as m1
    import measure_v2 as mv
    import metrics_v4 as mt
    od = out_dir(tag)
    if (od / "messages.jsonl").exists() and c.load_jsonl(od / "messages.jsonl"):
        await mv.run(m1.load_messages(od / "messages.jsonl"), od, mv4.EFFORT, 0, False)
    after = {r["item_id"]: r["verifier"] for r in c.load_jsonl(od / "measure.jsonl")} if (od / "measure.jsonl").exists() else {}
    before = {r["item_id"]: r["verifier"] for r in c.load_jsonl(mv4.DEV / tag / "measure.jsonl")}
    rows = {r["item_id"]: r for r in c.load_jsonl(od / "rounds.jsonl")}
    fits = mt.v4_fits()
    re_ids = sorted(after)
    L = [f"# 게이트 뒤 재작성 점검 — {tag} (보고용, 측정 범위 밖 경로)", "",
         "- 운영 품질 게이트 · 피드백 재작성을 그대로 돌렸다(DB 조회만 평가 스냅숏). 의미 유사도는 로컬 OpenSearch 인덱스 기준.",
         f"- 게이트 첫 판정 불통과 {sum(not r['rounds'][0]['passed'] for r in rows.values())}/{len(rows)}건 · 재작성 {len(re_ids)}건 · "
         f"최종 불통과 {sum(not r['final_passed'] for r in rows.values())}건", ""]
    m = sum(1 for i in rows if mt.matched(fits[i]) and not rows[i]["rounds"][0]["passed"])
    u = sum(1 for i in rows if not mt.matched(fits[i]) and not rows[i]["rounds"][0]["passed"])
    nm = sum(1 for i in rows if mt.matched(fits[i]))
    L.append(f"- 게이트 첫 판정 불통과(짝 층): 맞는 짝 {m}/{nm} · 안 맞는 짝 {u}/{len(rows) - nm}")
    for key, name in (("primary_positive", "주 지표"), ("llm_positive", "9개 유형")):
        b = sum(1 for i in re_ids if before[i][key])
        a = sum(1 for i in re_ids if after[i][key])
        L.append(f"- 재작성된 {len(re_ids)}건의 {name} 양성: 재작성 전 {b} → 후 {a}")
    (od / "rewrite_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("probe", "run", "verify"))
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    asyncio.run({"probe": _probe, "run": _run, "verify": _verify}[a.cmd](a.tag))


if __name__ == "__main__":
    main()
