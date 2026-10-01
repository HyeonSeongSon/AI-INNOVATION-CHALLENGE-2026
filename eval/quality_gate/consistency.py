"""
RQ4 일관성 — 같은 입력을 반복 판정하면 3단계 판정이 뒤집히는가.

(2026-09-29 플랜 8차 반영) 본 실행은 run_gate.py 의 low 5회 반복으로 RQ4 를 계산한다(analyze.py:
1회차로 경계선 선택, 2~5회차로만 측정). 이 스크립트는 시범(2회 반복)에서 쓴 별도 측정용으로 남긴다.

선택과 측정을 분리한다:
    - 선택: run_gate 의 운영 설정(기본 low) 1회차 결과로 경계선 케이스를 고른다
      (평균 3.6~4.4 또는 한 항목이라도 3점). 비경계 케이스는 시드 고정 무작위로 N건.
    - 측정: 고른 케이스를 같은 설정으로 새로 --repeats 회 판정한다. 선택에 쓴 1회차는 측정에 넣지 않는다.
1·2단계는 결정적이므로(run_gate 결정성 확인) 3단계만 반복한다.

사용법:
    python consistency.py --run pilot --effort low --repeats 5 --nonboundary 30
"""

import argparse
import asyncio
import json
import random
from typing import Any

from _common import bootstrap, load_jsonl, run_dir, write_jsonl

bootstrap()

from run_gate import SCORE_KEYS, fetch_products, judge, qc  # noqa: E402

DEFAULT_SEED = 20260929


def is_boundary(stage3: dict[str, Any]) -> bool:
    scores = stage3["scores"]
    return 3.6 <= scores["overall"] <= 4.4 or any(scores[k] == 3 for k in SCORE_KEYS)


async def main_async(args: argparse.Namespace) -> None:
    out_dir = run_dir(args.run)
    cases = {c["case_id"]: c for c in load_jsonl(out_dir / "cases.jsonl")}
    selection = {}
    for row in load_jsonl(out_dir / "gate_results.jsonl"):
        pick = next((s for s in row.get("stage3", []) if s["effort"] == args.effort and s["run"] == 1), None)
        if pick and not pick["missing"]:
            selection[row["case_id"]] = pick

    boundary = sorted(cid for cid, s in selection.items() if is_boundary(s))
    rest = sorted(cid for cid in selection if cid not in boundary)
    nonboundary = sorted(random.Random(args.seed).sample(rest, min(args.nonboundary, len(rest))))
    targets = [(cid, "boundary") for cid in boundary] + [(cid, "nonboundary") for cid in nonboundary]
    print(f"선택({args.effort} 1회차): 경계 {len(boundary)}건, 비경계 {len(nonboundary)}/{len(rest)}건 → 각 {args.repeats}회 측정")

    checker = qc.QualityChecker()
    products = await fetch_products(checker, {cases[cid]["product_id"] for cid, _ in targets})
    sem = asyncio.Semaphore(args.concurrency)
    jobs = [(cid, group, rep) for cid, group in targets for rep in range(1, args.repeats + 1)]
    measured = await asyncio.gather(*(
        judge(checker, cases[cid], products[cases[cid]["product_id"]], args.effort, 100 + rep, sem)
        for cid, _group, rep in jobs
    ))
    await checker.aclose()

    by_case: dict[str, list[dict[str, Any]]] = {}
    for (cid, _group, _rep), m in zip(jobs, measured):
        by_case.setdefault(cid, []).append(m)
    rows = [{
        "case_id": cid, "defect": cases[cid]["defect"], "level": cases[cid]["level"], "group": group,
        "selection": selection[cid], "measurements": by_case[cid],
    } for cid, group in targets]
    write_jsonl(out_dir / "consistency.jsonl", rows)
    (out_dir / "consistency_meta.json").write_text(json.dumps({
        "effort": args.effort, "repeats": args.repeats, "seed": args.seed,
        "n_boundary": len(boundary), "n_nonboundary": len(nonboundary), "n_nonboundary_pool": len(rest),
        "n_calls": sum(m["attempts"] for m in measured), "missing": sum(m["missing"] for m in measured),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    flips = sum(len({m["passed"] for m in ms if not m["missing"]}) > 1 for ms in by_case.values())
    print(f"뒤집힌 케이스 {flips}/{len(by_case)} → {out_dir / 'consistency.jsonl'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="pilot")
    parser.add_argument("--effort", default="low", help="운영값 (nodes.py quality_check_node)")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--nonboundary", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--concurrency", type=int, default=8)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
