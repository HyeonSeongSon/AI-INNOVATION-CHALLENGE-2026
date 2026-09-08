"""
풀 라벨만으로 가중치 컨피그를 비교하는 다운스트림 스코어링 — 재채점 없이 동작한다.

핵심 설계 결정 두 가지:
  · IDCG는 컨피그마다 다시 계산하지 않고, 페르소나당 한 번 그 페르소나의 풀 전체
    (모든 그리드 후보 + 하드네거티브) 라벨을 기준으로 고정한다. 컨피그 자신이 뽑은
    top_n 후보로 IDCG를 계산하면 분모가 컨피그마다 달라져 모든 NDCG가 1에 수렴한다.
  · compare_v4.py와 동일한 부트스트랩 95% CI(seed=7, B=2000, 페르소나 단위 리샘플)를
    계산해, 컨피그 간 차이가 노이즈인지 신호인지 구분한다. CI가 겹치면 승자를
    주장하지 않는다.

그리드 안의 컨피그는 pool.jsonl 구성상 전부 라벨이 보장되지만, --weights로 그리드
밖의 임의 컨피그를 실험하면 라벨 없는 후보가 나올 수 있다 — 그 경우 개수를 경고
출력하고 rel=0으로 처리한다(그리드에서 멀어질수록 풀링 편향이 조금씩 재도입됨).

사용법:
    python score_weight_grid.py
    python score_weight_grid.py --top-n 5
    python score_weight_grid.py --weights '{"retrieval":1.0,"need":1.15,"preference":1.1,"persona":1.0}'
"""

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from build_pool import ProductRecommender, synthesize_retrieval_dimension, CACHE_FILE, RESULT_DIR
from weight_grid import GRID_CONFIGS, RRF_K

from backend.app.config.settings import settings

OUTPUT_FILE = RESULT_DIR / "annotated_pool.jsonl"
SPLIT_FILE = RESULT_DIR / "split_pool.json"
SCORES_FILE = RESULT_DIR / "weight_grid_scores.json"

BOOTSTRAP_SEED = 7
BOOTSTRAP_B = 2000


# ─────────────────────────────────────────────
# 로드
# ─────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_cache_file() -> dict:
    if not CACHE_FILE.exists():
        return {}
    with open(CACHE_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_split() -> dict:
    if not SPLIT_FILE.exists():
        sys.exit(f"{SPLIT_FILE.name} 이 없습니다. make_pool_split.py 를 먼저 실행하세요.")
    with open(SPLIT_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_rel_and_persona_ratings() -> tuple[dict, dict[str, list[int]]]:
    """annotated_pool.jsonl → rel[(persona_id, product_id)] = rating,
    persona_ratings[persona_id] = 그 페르소나의 전체 라벨 리스트(IDCG 고정용)."""
    rel: dict[tuple, int] = {}
    for r in load_jsonl(OUTPUT_FILE):
        rel[(r["persona_id"], r["product_id"])] = r["rating"]

    persona_ratings: dict[str, list[int]] = defaultdict(list)
    for (persona_id, _product_id), rating in rel.items():
        persona_ratings[persona_id].append(rating)
    return rel, persona_ratings


# ─────────────────────────────────────────────
# NDCG / MRR
# ─────────────────────────────────────────────

def dcg_exp(rels: list[int]) -> float:
    """DCG = Σ (2^rel - 1) / log2(i+1), i는 1부터 시작."""
    return sum((2**r - 1) / math.log2(i + 1) for i, r in enumerate(rels, start=1))


def ndcg_at(selected_rels: list[int], ideal_rels: list[int]) -> float:
    idcg = dcg_exp(ideal_rels)
    if idcg == 0:
        return 0.0
    return dcg_exp(selected_rels) / idcg


def score_config(
    weights: dict,
    personas: list[str],
    rel: dict,
    persona_ratings: dict[str, list[int]],
    cache: dict,
    top_n: int,
) -> tuple[dict[str, float], dict[str, float], int]:
    persona_ndcg: dict[str, float] = {}
    persona_mrr: dict[str, float] = {}
    unjudged_count = 0

    for persona_id in personas:
        cached = cache.get(persona_id)
        if cached is None:
            continue

        dr = synthesize_retrieval_dimension(cached)
        ranked = ProductRecommender._apply_rrf(dr, weights=weights, k=RRF_K)[:top_n]

        selected_rels: list[int] = []
        first_rel2_rank: int | None = None
        for rank, (pid, _score) in enumerate(ranked, start=1):
            r = rel.get((persona_id, pid))
            if r is None:
                unjudged_count += 1
                r = 0
            selected_rels.append(r)
            if r == 2 and first_rel2_rank is None:
                first_rel2_rank = rank

        ideal_rels = sorted(persona_ratings.get(persona_id, []), reverse=True)[:top_n]
        persona_ndcg[persona_id] = ndcg_at(selected_rels, ideal_rels)
        persona_mrr[persona_id] = (1.0 / first_rel2_rank) if first_rel2_rank else 0.0

    return persona_ndcg, persona_mrr, unjudged_count


def bootstrap_ci(values_by_key: dict[str, float], seed: int = BOOTSTRAP_SEED, b: int = BOOTSTRAP_B):
    keys = list(values_by_key.keys())
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = []
    for _ in range(b):
        sample = [values_by_key[keys[rng.randrange(len(keys))]] for _ in keys]
        means.append(statistics.mean(sample))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return lo, hi


# ─────────────────────────────────────────────
# 리포트
# ─────────────────────────────────────────────

def print_report(results: dict, top_n: int) -> None:
    sep = "=" * 78
    print(sep)
    print(f" 가중치 그리드 스코어링 — NDCG@{top_n} / MRR ± 95% 부트스트랩 CI (B={BOOTSTRAP_B})")
    print(sep)

    for subset_name in ("dev", "heldout"):
        print(f"\n[{subset_name}]")
        print(f"  {'config':<28}  {'n':>4}  {'NDCG':>8}  {'95% CI':>20}  {'MRR':>8}  {'unjudged':>8}")
        print(f"  {'-' * 28}  {'-' * 4}  {'-' * 8}  {'-' * 20}  {'-' * 8}  {'-' * 8}")
        for config_name, row in results.items():
            r = row[subset_name]
            ci_str = f"[{r['ndcg_ci'][0]:.4f}, {r['ndcg_ci'][1]:.4f}]"
            print(
                f"  {config_name:<28}  {r['n_personas']:>4}  {r['ndcg_mean']:>8.4f}  "
                f"{ci_str:>20}  {r['mrr_mean']:>8.4f}  {r['unjudged']:>8}"
            )

    if "current_default" in results:
        print("\n[current_default 대비 CI 겹침 여부 — 겹치지 않을 때만 승자를 주장한다]")
        for subset_name in ("dev", "heldout"):
            base_ci = results["current_default"][subset_name]["ndcg_ci"]
            base_mean = results["current_default"][subset_name]["ndcg_mean"]
            print(f"  {subset_name}:")
            for config_name, row in results.items():
                if config_name == "current_default":
                    continue
                ci = row[subset_name]["ndcg_ci"]
                overlap = not (ci[1] < base_ci[0] or ci[0] > base_ci[1])
                if overlap:
                    print(f"    {config_name:<28} vs current_default : 겹침 — 차이가 노이즈 범위 내")
                else:
                    better = "우위" if row[subset_name]["ndcg_mean"] > base_mean else "열위"
                    print(f"    {config_name:<28} vs current_default : 겹치지 않음 → {better}")


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=None,
                         help="기본: settings.product_recommendation_top_n (production과 동일)")
    parser.add_argument("--weights", type=str, default=None,
                         help='임의 컨피그 JSON 1개, 예: \'{"retrieval":1.0,"need":1.15,"preference":1.1,"persona":1.0}\' '
                              '(미지정 시 weight_grid.GRID_CONFIGS 전체를 스코어링)')
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    top_n = args.top_n if args.top_n is not None else settings.product_recommendation_top_n

    cache = load_cache_file()
    if not cache:
        sys.exit(f"{CACHE_FILE.name} 이 없습니다. build_pool.py 를 먼저 실행하세요.")

    rel, persona_ratings = build_rel_and_persona_ratings()
    if not rel:
        sys.exit(f"{OUTPUT_FILE.name} 이 없습니다. annotate_pool.py 로 먼저 채점하세요.")

    split = load_split()

    if args.weights:
        configs = {"custom": json.loads(args.weights)}
    else:
        configs = GRID_CONFIGS

    results: dict[str, dict] = {}
    for config_name, weights in configs.items():
        row: dict[str, dict] = {}
        for subset_name in ("dev", "heldout"):
            personas = split.get(subset_name, [])
            persona_ndcg, persona_mrr, unjudged = score_config(
                weights, personas, rel, persona_ratings, cache, top_n
            )
            if unjudged:
                print(
                    f"  ⚠ [{config_name}/{subset_name}] unjudged 후보 {unjudged}건 → rel=0 처리 "
                    f"(그리드 밖 컨피그이거나 아직 전량 채점되지 않았을 가능성)"
                )
            ndcg_lo, ndcg_hi = bootstrap_ci(persona_ndcg)
            row[subset_name] = {
                "ndcg_mean": statistics.mean(persona_ndcg.values()) if persona_ndcg else 0.0,
                "ndcg_ci": [ndcg_lo, ndcg_hi],
                "mrr_mean": statistics.mean(persona_mrr.values()) if persona_mrr else 0.0,
                "n_personas": len(persona_ndcg),
                "unjudged": unjudged,
            }
        results[config_name] = row

    print_report(results, top_n)

    out_path = Path(args.out) if args.out else SCORES_FILE
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"top_n": top_n, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out_path.name}")


if __name__ == "__main__":
    main()
