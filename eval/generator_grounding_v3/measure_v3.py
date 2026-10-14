"""
v3 개발 라운드 추가 지표 — measure_v2 는 그대로 쓰고(잠김) 여기서는 덧붙이는 것만 둔다.

- regex_metrics_v3: v2 정리 정규식 + 변화 암시 제목에 '달라질 · 달라지' 추가(N045 '달라질까' 누락 보완)
- 프롬프트 예시 복제율: 각 버전 프롬프트 소스의 따옴표 안 문구(공백 제외 6자 이상)가 제목 · CTA 에 그대로 있는지
- CTA · 제목 구조 다양성: 앞 두 어절 상위 1개 비율, CTA 끝 어절 종류 수, CTA "지금" 비율(진단용)
- 판정기 재판정: measure.judge 와 같은 호출(checker._run_llm_judge)에 feedback 까지 보관
"""

import asyncio
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import v3_common as v3  # noqa: F401
from gg_common import load_jsonl

import measure as m1  # noqa: E402
import measure_v2 as mv  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402

CLEANUP = ("number_mutation", "review_verified", "change_hook_title", "test_kind_missing")


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def regex_metrics_v3(m: dict[str, Any], brand_profile: str) -> dict[str, Any]:
    out = mv.regex_metrics_v2(m, brand_profile)
    full = mv.snapshot_text(m["product_snapshot"])
    has_change = bool(re.search(r"리뉴얼|기존|업그레이드|새로워|강화된|개선된|업데이트", full))
    out["change_hook_title"] = [] if has_change else \
        [squash(x) for x in re.findall(r"달라진|달라졌|달랐던|달라질|달라지|새로워진|바뀐", m.get("title", ""))]
    out["cleanup_any"] = any(out[k] for k in CLEANUP)
    return out


def cta_text(m: dict[str, Any]) -> str:
    sents = m1.review_kit.split_sentences(m.get("message", ""))
    return sents[-1] if sents else ""


def prompt_quotes(src: str) -> list[str]:
    """프롬프트 소스의 따옴표 안 문구 중 공백 제외 6자 이상(긍정 · 부정 예시 모두)."""
    qs = {squash(q) for q in re.findall(r'"([^"{}\n]{4,60})"', src)}
    return sorted(q for q in qs if len(q) >= 6)


def example_copy(m: dict[str, Any], quotes: list[str]) -> list[str]:
    t, c = squash(m.get("title", "")), squash(cta_text(m))
    return [q for q in quotes if q in t or q in c]


def first2(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s가-힣]", " ", s).split()[:2])


def structure(msgs: list[dict[str, Any]]) -> dict[str, Any]:
    ctas = [cta_text(m) for m in msgs]
    heads = Counter(first2(c) for c in ctas)
    tails = Counter((re.sub(r"[^\w가-힣]", " ", c).split() or [""])[-1] for c in ctas)
    titles = Counter(first2(m.get("title", "")) for m in msgs)
    n = len(msgs) or 1
    return {"cta_head_top1": heads.most_common(1)[0] if heads else ("", 0), "cta_head_top1_share": (heads.most_common(1)[0][1] / n) if heads else 0,
            "cta_tail_kinds": len(tails), "cta_tail_top1": tails.most_common(1)[0] if tails else ("", 0),
            "title_head_top1": titles.most_common(1)[0] if titles else ("", 0),
            "title_head_top1_share": (titles.most_common(1)[0][1] / n) if titles else 0,
            "cta_now": sum("지금" in c for c in ctas)}


async def judge_fb(checker: Any, m: dict[str, Any], run: int, sem: asyncio.Semaphore) -> dict[str, Any]:
    """measure.judge 와 같은 호출 · 재시도. feedback 을 함께 남긴다."""
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier, reasoning_effort="low")
    snap = m["product_snapshot"]
    async with sem:
        attempts, latencies, scores, passed = 0, [], None, False
        while attempts < 2:
            attempts += 1
            t0 = time.perf_counter()
            passed, scores = await checker._run_llm_judge(
                m.get("title", ""), m.get("message", ""), snap.get("product_name", ""), snap, m["purpose"],
                m["brand"], llm, persona_info=m["persona_info"],
            )
            latencies.append(round(time.perf_counter() - t0, 2))
            if scores and "accuracy" in scores:
                break
    missing = not (scores and "accuracy" in scores)
    return {"item_id": m["item_id"], "run": run, "missing": missing, "passed": None if missing else passed,
            "scores": None if missing else {k: scores[k] for k in (*m1.SCORE_KEYS, "overall")},
            "feedback": (scores or {}).get("feedback", ""), "attempts": attempts, "latency_s": latencies}


async def rejudge(messages: list[dict[str, Any]], path: Path, runs: int = 2) -> list[dict[str, Any]]:
    import run_d1
    checker = run_d1.make_detector()
    done = {(r["item_id"], r["run"]): r for r in load_jsonl(path) if not r.get("missing")} if path.exists() else {}
    sem = asyncio.Semaphore(m1.JUDGE_CONCURRENCY)
    lock = asyncio.Lock()
    path.parent.mkdir(parents=True, exist_ok=True)

    async def one(m, k):
        rec = await judge_fb(checker, m, k, sem)
        async with lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if not rec["missing"]:
            done[(m["item_id"], k)] = rec

    jobs = [(m, k) for m in messages for k in range(1, runs + 1) if (m["item_id"], k) not in done]
    print(f"  판정기 {len(jobs)}회 → {path.name}", flush=True)
    await asyncio.gather(*(one(m, k) for m, k in jobs))
    return [done[(m["item_id"], k)] for m in messages for k in range(1, runs + 1) if (m["item_id"], k) in done]
