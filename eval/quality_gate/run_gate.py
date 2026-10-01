"""
실제 QualityChecker 로 케이스를 판정한다 — 단계별로 각각 호출해 기록하고, 파이프라인 판정은
check_quality 와 같은 순서(1단계 → 2단계 → 3단계, 첫 실패에서 멈춤)로 analyze.py 에서 도출한다.

- 상품 조회: 실제 ProductClient (로컬 DB API :8020).
- 1단계: _run_rule_check. 바꾼 문장(changed_sentences)에서 나온 검출을 문장 단위로 따로 기록한다:
  changed_hits = 전체 검출 ∩ 바꾼 문장 단독 검출(올바른 사유 · 멈춤 규칙 비교용),
  cross_boundary_hits = 전체 검출 − 원본 전체 검출 − changed_hits (형태소 매칭이 문장 경계를 넘은 것,
  멈춤 사유 아님 — "건조해진 피부. 치료 후…"가 "피부 치료"에 걸린다).
- 2단계: 실제 OpenSearch 경로(_run_semantic_similarity_check, ANN k=3) — 보조 판정 · 동등성 확인용.
  override 켬/끔은 모듈 함수 _is_hedge_without_assertion 을 바꿔 끼워 두 번 판정한다. 같은 입력이 두 번
  검색되지 않도록 _search_sentences_batch 를 문장 튜플 단위로 캐시한다.
  문장별 전수 최근접(top_k=100)을 함께 기록하고, **주 판정은 전수 기준**이다(exact_on / exact_off).
  로컬 HNSW 그래프는 EC2 색인과 달라 ANN 결과는 재현을 보장하지 않는다.
- 3단계: _run_llm_judge 를 설정별 반복 횟수만큼 호출(--schedule, 기본 low 5 · medium 3 · minimal 3).
  원본 속 D1(보조)은 --d1-schedule(기본 low 2)만. 점수 키가 없는 결과(예외 폴백)는 1회 더 시도하고,
  그래도 없으면 결측으로 기록한다(불통과로 세지 않는다).
- 동등성 확인: 케이스마다 check_quality(llm=None) 를 불러 1·2단계 결과와 실패 단계가 **ANN 기준**
  도출값과 같은지 기록한다(check_quality 는 ANN 을 쓴다). 전수 대 ANN 불일치는 따로 센다.

사용법 (Python 3.11):
    python run_gate.py --run main --schedule low:5,medium:3,minimal:3 --d1-schedule low:2 --concurrency 8
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from _common import REPO_ROOT, bootstrap, gate_sentences, load_jsonl, run_dir, stage2_exact_top1, write_jsonl

bootstrap()

import httpx  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.prompts.quality_check_prompt import build_quality_check_prompt  # noqa: E402
from app.agents.generate_message_agent.services import quality_check as qc  # noqa: E402

SCORE_KEYS = ("accuracy", "tone", "personalization", "naturalness", "cta_clarity")

_search_cache: dict[tuple[str, ...], Any] = {}
_original_search_batch = qc.QualityChecker._search_sentences_batch
_original_hedge_fn = qc._is_hedge_without_assertion


async def _cached_search_batch(self, client, sentences, endpoint):
    key = tuple(sentences)
    if key not in _search_cache:
        _search_cache[key] = await _original_search_batch(self, client, sentences, endpoint)
    return _search_cache[key]


qc.QualityChecker._search_sentences_batch = _cached_search_batch


def _git_meta() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "tracked_changes": git("diff", "--name-only", "HEAD").splitlines()}


def _sent_params(effort: str) -> dict[str, Any]:
    """실제 전송 파라미터 — langchain 이 OpenAI 로 보낼 payload 에서 messages 만 뺀 것."""
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier, reasoning_effort=effort)
    payload = llm._get_request_payload([HumanMessage(content="ping")])
    payload.pop("messages", None)
    return payload


def _prompt_hash() -> dict[str, str]:
    system_prompt, _ = build_quality_check_prompt("b", "p", {}, "x", "t", "t", "m")
    schema = json.dumps(qc.LLMJudgeOutput.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return {
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "judge_schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest(),
    }


def parse_schedule(text: str) -> dict[str, int]:
    """"low:5,medium:3" → {"low": 5, "medium": 3} (순서 유지)."""
    out = {}
    for part in text.split(","):
        effort, runs = part.split(":")
        out[effort.strip()] = int(runs)
    return out


async def stage1_and_2(checker: qc.QualityChecker, case: dict[str, Any], http: httpx.AsyncClient) -> dict[str, Any]:
    title, message = case["title"], case["message"]
    changed = case.get("changed_sentences") or ([case["injected_sentence"]] if case.get("injected_sentence") else [])
    thr = settings.quality_check_semantic_threshold

    passed1, issues = checker._run_rule_check(title, message)
    detected = checker._detect_forbidden_expressions(f"{title} {message}")
    alone = set()
    for sent in changed:
        alone |= set(checker._detect_forbidden_expressions(sent))
    changed_hits = sorted(set(detected) & alone)
    orig_detected = set(checker._detect_forbidden_expressions(
        f"{case.get('original_title', title)} {case.get('original_message', message)}"))
    cross_boundary = sorted(set(detected) - orig_detected - set(changed_hits))

    qc._is_hedge_without_assertion = _original_hedge_fn
    passed_on, triggered_on = await checker._run_semantic_similarity_check(title, message)
    qc._is_hedge_without_assertion = lambda _s: False
    passed_off, triggered_off = await checker._run_semantic_similarity_check(title, message)
    qc._is_hedge_without_assertion = _original_hedge_fn

    sentences = gate_sentences(title, message)
    raw = _search_cache.get(tuple(sentences))
    api_error = raw is None
    injected_pieces = {piece for sent in changed for piece in gate_sentences("", sent)}
    per_sentence = []
    if not api_error:
        exact = await stage2_exact_top1(http, sentences)
        for s, results, ex in zip(sentences, raw, exact):
            top = max(results, key=lambda r: r["score"]) if results else {}
            per_sentence.append({
                "sentence": s,
                "ann_top1": top.get("score", 0.0), "ann_matched": top.get("matched_sentence"),
                "exact_top1": ex["score"], "exact_matched": ex["matched"],
                "hedge_override": _original_hedge_fn(s),
                "is_injected": s in injected_pieces,
            })

    def exact_verdict(override: bool) -> dict[str, Any]:
        """전수 기준 2단계 판정(주 판정). override=True 면 헷지 조건이 성립한 문장은 무시한다."""
        hits = [x for x in per_sentence if x["exact_top1"] > thr and not (override and x["hedge_override"])]
        return {"passed": not hits, "triggered": [x["sentence"] for x in hits],
                "injected_triggered": any(x["is_injected"] for x in hits)}

    def summarize(passed: bool, triggered: list[dict[str, Any]]) -> dict[str, Any]:
        hits = [r for r in triggered if "query_sentence" in r]
        return {
            "passed": passed,
            "triggered": [{"query": r["query_sentence"], "matched": r["matched_sentence"], "score": r["score"]} for r in hits],
            "injected_triggered": any(r["query_sentence"] in injected_pieces for r in hits),
        }

    # 동등성 확인: 실제 check_quality (llm=None → 3단계 직전에서 멈춤)
    real = await checker.check_quality(
        message={"title": title, "message": message}, product_id=case["product_id"],
        purpose=case["purpose"], llm=None, persona_info=case["persona_info"],
    )
    derived_stage = "rule_check" if not passed1 else ("semantic_check" if not passed_on else "llm_judge")
    return {
        "stage1": {"passed": passed1, "issues": issues, "detected": detected,
                   "injected_hits": changed_hits, "cross_boundary_hits": cross_boundary},
        "stage2": {
            "api_error": api_error,
            "override_on": summarize(passed_on, triggered_on),
            "override_off": summarize(passed_off, triggered_off),
            "exact_on": None if api_error else exact_verdict(True),
            "exact_off": None if api_error else exact_verdict(False),
            "sentences": per_sentence,
        },
        "equivalence": {
            "check_quality_failed_stage": real["failed_stage"],
            "derived_failed_stage": derived_stage,
            "match": real["failed_stage"] == derived_stage
            and real["rule_check_passed"] == passed1
            and (not passed1 or real["semantic_check_passed"] == passed_on),
        },
    }


async def judge(checker: qc.QualityChecker, case: dict[str, Any], product: dict[str, Any], effort: str, run: int,
                sem: asyncio.Semaphore) -> dict[str, Any]:
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier, reasoning_effort=effort)
    async with sem:
        attempts, latencies = 0, []
        scores: dict[str, Any] | None = None
        passed = False
        while attempts < 2:
            attempts += 1
            t0 = time.perf_counter()
            passed, scores = await checker._run_llm_judge(
                case["title"], case["message"], product["product_name"], product["flat"], case["purpose"],
                product["brand"], llm, persona_info=case["persona_info"],
            )
            latencies.append(round(time.perf_counter() - t0, 2))
            if scores and "accuracy" in scores:
                break
    missing = not (scores and "accuracy" in scores)
    return {
        "effort": effort, "run": run, "missing": missing, "passed": None if missing else passed,
        "scores": None if missing else {k: scores[k] for k in (*SCORE_KEYS, "overall")},
        "feedback": None if missing else scores.get("feedback"),
        "attempts": attempts, "latency_s": latencies,
    }


async def fetch_products(checker: qc.QualityChecker, product_ids: set[str]) -> dict[str, dict[str, Any]]:
    """check_quality 와 같은 방식으로 상품 조회 → flatten."""
    products: dict[str, dict[str, Any]] = {}
    for pid in sorted(product_ids):
        db = await checker._product_client.get_products_detail_from_db([pid])
        if not db:
            raise RuntimeError(f"상품 조회 실패: {pid}")
        products[pid] = {
            "flat": checker._product_client.flatten_product_data(db[0]),
            "product_name": db[0].get("product_name", ""), "brand": db[0].get("brand", ""),
        }
    return products


async def main_async(args: argparse.Namespace) -> None:
    out_dir = run_dir(args.run)
    cases = [c for c in load_jsonl(out_dir / "cases.jsonl") if c["valid"] or args.include_invalid]
    if args.limit:
        cases = cases[: args.limit]
    schedule = parse_schedule(args.schedule)
    d1_schedule = parse_schedule(args.d1_schedule)
    efforts = list(dict.fromkeys([*schedule, *d1_schedule]))

    checker = qc.QualityChecker()
    products = await fetch_products(checker, {c["product_id"] for c in cases})

    # 2단계 결정성 사전 확인: 캐시를 거치지 않고 같은 배치를 3번 검색
    probe = gate_sentences(cases[0]["title"], cases[0]["message"])
    endpoint = f"{settings.opensearch_api_url}/api/search/similar-sentences/batch"
    probes = [await _original_search_batch(checker, checker.http_client, probe, endpoint) for _ in range(3)]
    stage2_deterministic = all(p == probes[0] for p in probes)
    print(f"2단계 결정성(같은 배치 3회): {stage2_deterministic}")

    results: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=60, headers={"X-Internal-Token": settings.internal_token}) as http:
        for c in cases:  # override 토글이 모듈 전역이므로 1·2단계는 순차 실행
            results[c["case_id"]] = await stage1_and_2(checker, c, http)
    print(f"1·2단계 완료 {len(cases)}건, 동등성 불일치 {sum(not r['equivalence']['match'] for r in results.values())}건")

    sem = asyncio.Semaphore(args.concurrency)
    jobs = [(c, e, r) for c in cases
            for e, n in (d1_schedule if c["defect"] == "D1" else schedule).items()
            for r in range(1, n + 1)] if not args.no_judge else []
    t0 = time.perf_counter()
    judged = await asyncio.gather(*(judge(checker, c, products[c["product_id"]], e, r, sem) for c, e, r in jobs))
    wall = round(time.perf_counter() - t0, 1)
    for (c, _e, _r), j in zip(jobs, judged):
        results[c["case_id"]].setdefault("stage3", []).append(j)
    await checker.aclose()

    rows = [{
        "case_id": c["case_id"], "original_id": c["original_id"], "defect": c["defect"], "level": c["level"],
        **results[c["case_id"]],
    } for c in cases]
    write_jsonl(out_dir / "gate_results.jsonl", rows)
    meta = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "git": _git_meta(),
        "model": settings.chatgpt_model_name,
        "temperature_setting": settings.llm_temperature_classifier,
        "sent_params": {e: _sent_params(e) for e in efforts},
        "prompt": _prompt_hash(),
        "gate_settings": {
            "semantic_threshold": settings.quality_check_semantic_threshold,
            "semantic_top_k": settings.quality_check_semantic_top_k,
            "llm_min_score": settings.quality_check_llm_min_score,
            "llm_min_overall_score": settings.quality_check_llm_min_overall_score,
            "body_len": [settings.message_body_min_length, settings.message_body_max_length],
            "title_max": settings.message_title_max_length,
        },
        "stage2_path": "주 판정: 문장별 전수 top1(top_k=100) · 보조: OpenSearch ANN k=3 (forbidden_sentences, replicas=0)",
        "stage2_deterministic_probe": stage2_deterministic,
        "efforts": efforts, "schedule": schedule, "d1_schedule": d1_schedule,
        "runs": max(schedule.values()), "concurrency": args.concurrency,
        "n_cases": len(cases), "n_judge_jobs": len(jobs), "judge_wall_s": wall,
        "judge_missing": sum(j["missing"] for j in judged),
        "judge_attempts_total": sum(j["attempts"] for j in judged),
    }
    (out_dir / "gate_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"3단계 {len(jobs)}건 ({wall}s), 결측 {meta['judge_missing']}건, 총 호출 {meta['judge_attempts_total']}회")
    print(f"→ {out_dir / 'gate_results.jsonl'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="pilot")
    parser.add_argument("--schedule", default="low:5,medium:3,minimal:3",
                        help="설정별 3단계 반복 횟수(원본 속 D1 제외). 운영값은 low")
    parser.add_argument("--d1-schedule", default="low:2", help="원본 속 D1(보조)의 3단계 반복 횟수")
    parser.add_argument("--no-judge", action="store_true", help="1·2단계만 돌린다(LLM 호출 없음, 스모크 확인용)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (스모크 테스트용)")
    parser.add_argument("--include-invalid", action="store_true")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
