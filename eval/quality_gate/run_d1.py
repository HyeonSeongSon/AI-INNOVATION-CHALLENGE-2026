"""
D1 문구 집합을 문장 단독으로 1·2단계에 돌린다 — 사전 등록 1(D1 주 지표) · 3(RQ2 우회 경로). LLM 호출 없음.

문장마다 기록하는 것 (맨 문구 · 틀을 채운 문장 · 헷지 층 표적 시험용 틀별 문장):
    - 1단계: _detect_forbidden_expressions(문장 단독) 검출 키워드. 길이 규칙은 적용하지 않는다.
    - 2단계: 전수 1위(top_k=100, 주 판정) · ANN 1위(k=3, 게이트 경로, 보조) 점수와 매칭 문장,
      override 조건(_is_hedge_without_assertion).
    - 판정: 2단계 불통과 = 점수 > 임계값이고 (override 켬이면) 조건 불성립. 전수 · ANN × 켬 · 끔 네 가지.
      탐지 = 1단계 검출 또는 2단계 불통과.
1·2단계는 결정적이다(run_gate 결정성 확인). 같은 문장은 한 번만 검색한다.

사용법:
    python run_d1.py --run main
출력: result/<run>/d1_results.jsonl, d1_meta.json
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone

from _common import bootstrap, gate_sentences, load_jsonl, run_dir, stage2_topk, write_jsonl

bootstrap()

import httpx  # noqa: E402
from kiwipiepy import Kiwi  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.agents.generate_message_agent.services import quality_check as qc  # noqa: E402


def make_detector() -> qc.QualityChecker:
    """1단계 검출기만 쓰는 QualityChecker — 네트워크 클라이언트를 만들지 않는다."""
    checker = qc.QualityChecker.__new__(qc.QualityChecker)
    checker._forbidden_expressions = checker._extract_forbidden_expressions()
    checker._kiwi = Kiwi()
    checker._automaton = checker._build_automaton()
    return checker


def verdicts(stage1_hits: list[str], exact: float, ann: float, cond: bool, thr: float) -> dict[str, bool]:
    out = {}
    for basis, score in (("exact", exact), ("ann", ann)):
        out[f"s2_{basis}_off"] = score > thr
        out[f"s2_{basis}_on"] = score > thr and not cond
        out[f"detected_{basis}_on"] = bool(stage1_hits) or out[f"s2_{basis}_on"]
        out[f"detected_{basis}_off"] = bool(stage1_hits) or out[f"s2_{basis}_off"]
    return out


async def main_async(args: argparse.Namespace) -> None:
    out_dir = run_dir(args.run)
    items = load_jsonl(out_dir / "d1_set.jsonl")
    thr = settings.quality_check_semantic_threshold
    detector = make_detector()

    sentences = sorted({s for it in items for s in (it["bare"], it["sentence"], *(t["sentence"] for t in it["targeted"]))})
    bad_split = [s for s in sentences if len(gate_sentences("", s)) != 1]
    if bad_split:
        raise SystemExit(f"게이트 문장 분리로 한 문장이 아닌 문장이 있습니다(make_d1_set 검사 누락): {bad_split[:3]}")
    queries = [gate_sentences("", s)[0] for s in sentences]
    async with httpx.AsyncClient(timeout=120, headers={"X-Internal-Token": settings.internal_token}) as http:
        exact, ann = [], []
        for i in range(0, len(queries), 50):
            chunk = queries[i:i + 50]
            exact += await stage2_topk(http, chunk, 100)
            ann += await stage2_topk(http, chunk, settings.quality_check_semantic_top_k)

    evald = {}
    for s, q, ex, an in zip(sentences, queries, exact, ann):
        hits = detector._detect_forbidden_expressions(s)
        cond = qc._is_hedge_without_assertion(q)
        e1 = ex[0] if ex else {"score": 0.0, "sentence": None}
        a1 = an[0] if an else {"score": 0.0, "sentence": None}
        evald[s] = {
            "sentence": s, "stage1_hits": hits,
            "exact_top1": e1["score"], "exact_matched": e1["sentence"],
            "ann_top1": a1["score"], "ann_matched": a1["sentence"],
            "override_condition": cond,
            **verdicts(hits, e1["score"], a1["score"], cond, thr),
        }

    rows = []
    for it in items:
        rows.append({
            **{k: it[k] for k in ("item_id", "role", "phrase_id", "stratum", "category", "kind", "source",
                                  "template_type", "template_source", "hedge_basis")},
            "original_id": it.get("original_id"), "slot": it.get("slot"),
            "bare": evald[it["bare"]], "templated": evald[it["sentence"]],
            "targeted": [{"type": t["type"], **evald[t["sentence"]]} for t in it["targeted"]],
            "keyword_in_phrase": bool(evald[it["bare"]]["stage1_hits"]),
        })
    write_jsonl(out_dir / "d1_results.jsonl", rows)
    meta = {
        "run_at": datetime.now(timezone.utc).isoformat(), "threshold": thr,
        "ann_top_k": settings.quality_check_semantic_top_k, "exact_top_k": 100,
        "n_items": len(items), "n_unique_sentences": len(sentences),
    }
    (out_dir / "d1_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    prim = [r for r in rows if r["role"] == "primary"]
    det = sum(r["templated"]["detected_exact_on"] for r in prim)
    print(f"D1 주 문구 {len(prim)}개: 탐지(전수·켬) {det} · 원본 속 {len(rows) - len(prim)}개 → {out_dir / 'd1_results.jsonl'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="main")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
