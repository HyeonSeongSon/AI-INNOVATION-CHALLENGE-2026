"""
페르소나별 dimension_results 를 1회 fetch해 캐시하고, weight_grid.GRID_CONFIGS
전체를 추가 네트워크 호출 없이 스윕해 pool.jsonl(풀 채점 대상)을 만든다.

핵심 사실: ProductRecommender._apply_rrf 는 순수 인메모리 재계산이라, 페르소나당
dimension_results(need/preference/persona + retrieval)를 한 번만 가져오면
가중치 조합은 몇 개든 로컬에서 스윕 가능하다 (recommend_product_in_persona.py:238-266).

사용법:
    python build_pool.py
    python build_pool.py --concurrency 3
    python build_pool.py --force        # 캐시 무시하고 전건 재수집
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

sys.stdout.reconfigure(encoding="utf-8")

from backend.app.agents.recommend_product_agent.services.recommend_product_in_persona import ProductRecommender

from weight_grid import (
    GRID_CONFIGS,
    RRF_K,
    TOP_K_PER_CONFIG,
    N_HARD_NEGATIVES,
    HARD_NEG_RANK_RANGE,
)
from seed_eval_personas import ensure_test_user

BASE_DIR = Path(__file__).parent
RESULT_DIR = BASE_DIR / "result"
PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"
TAG_MAP_FILE = BASE_DIR / "tag_normalize.json"
CACHE_FILE = RESULT_DIR / "dimension_results_cache.json"
POOL_FILE = RESULT_DIR / "pool.jsonl"

DEFAULT_CONCURRENCY = 5


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_tag_normalizer():
    """페르소나 product_tag를 실제 상품 tag 표기로 정규화 (judge_v4.py와 동일 파일/패턴)."""
    with open(TAG_MAP_FILE, encoding="utf-8") as f:
        mapping = json.load(f)["persona_to_product"]

    def normalize(tag: str | None) -> str:
        t = (tag or "").strip()
        return mapping.get(t, t)

    return normalize


# ─────────────────────────────────────────────
# Step 1 — 페르소나당 1회 fetch
# ─────────────────────────────────────────────

async def fetch_dimension_results(
    persona_id: str, product_tag: str, recommender: ProductRecommender, user_id: str | None, normalize
) -> dict | None:
    queries = await recommender.get_product_search_queries(persona_id, user_id=user_id)
    if queries is None:
        return None
    retrieval_ids = await recommender.product_retriever(
        retrieval_query=queries["retrieval"],
        brands=None,
        sub_tags=[normalize(product_tag)],
        retrieval_vector=None,
    )
    dimension_results = await recommender.get_product_documents(
        queries, retrieval_ids, query_vectors=None
    )
    return {"retrieval_result_ids": retrieval_ids, "dimension_results": dimension_results}


async def fetch_one(
    record: dict,
    recommender: ProductRecommender,
    semaphore: asyncio.Semaphore,
    done_ref: list,
    total: int,
    user_id: str | None,
    normalize,
) -> tuple[str, dict | None]:
    persona_id = record["persona_id"]
    product_tag = record["product_tag"]
    async with semaphore:
        try:
            result = await fetch_dimension_results(persona_id, product_tag, recommender, user_id, normalize)
            done_ref[0] += 1
            status = "ok" if result else "쿼리 캐시 없음"
            print(f"[{done_ref[0]}/{total}] {persona_id} ({product_tag}) — {status}")
            return persona_id, result
        except Exception as e:
            done_ref[0] += 1
            print(f"[{done_ref[0]}/{total}] {persona_id} 실패 — {type(e).__name__}")
            return persona_id, None


# ─────────────────────────────────────────────
# Step 2 — 스윕 (네트워크 없음)
# ─────────────────────────────────────────────

def synthesize_retrieval_dimension(cached: dict) -> dict:
    """recommend()의 retrieval 차원 합성과 동일 (recommend_product_in_persona.py:294-297)."""
    dr = dict(cached["dimension_results"])
    dr["retrieval"] = [{"product_id": pid} for pid in cached["retrieval_result_ids"]]
    return dr


def sweep_configs(dr: dict) -> dict[str, dict[str, int]]:
    """그리드 컨피그 전체로 RRF 재계산 → {product_id: {config_name: rank}}."""
    candidate_ranks: dict[str, dict[str, int]] = {}
    for config_name, weights in GRID_CONFIGS.items():
        ranked = ProductRecommender._apply_rrf(dr, weights=weights, k=RRF_K)[:TOP_K_PER_CONFIG]
        for rank, (pid, _score) in enumerate(ranked, start=1):
            candidate_ranks.setdefault(pid, {})[config_name] = rank
    return candidate_ranks


# ─────────────────────────────────────────────
# Step 3 — 하드 네거티브
# ─────────────────────────────────────────────

def pick_hard_negatives(
    retrieval_ids: list[str], candidate_ranks: dict, seed: int
) -> list[str]:
    lo, hi = HARD_NEG_RANK_RANGE
    tail = retrieval_ids[lo - 1 : hi]  # 1-idx 구간(20~50위) → 0-idx 슬라이스
    tail_free = [pid for pid in tail if pid not in candidate_ranks]
    rng = random.Random(seed)
    return rng.sample(tail_free, min(N_HARD_NEGATIVES, len(tail_free)))


def build_pool_records(persona_id: str, product_tag: str, cached: dict, seed: int) -> list[dict]:
    dr = synthesize_retrieval_dimension(cached)
    candidate_ranks = sweep_configs(dr)
    retrieval_ids = cached["retrieval_result_ids"]
    retrieval_rank_of = {pid: i + 1 for i, pid in enumerate(retrieval_ids)}
    hard_negatives = pick_hard_negatives(retrieval_ids, candidate_ranks, seed)

    records = []
    for pid, configs in candidate_ranks.items():
        records.append({
            "persona_id": persona_id,
            "product_tag": product_tag,
            "product_id": pid,
            "configs": configs,
            "n_configs_hit": len(configs),
            "is_hard_negative": False,
            "retrieval_rank": retrieval_rank_of.get(pid),
        })
    for pid in hard_negatives:
        records.append({
            "persona_id": persona_id,
            "product_tag": product_tag,
            "product_id": pid,
            "configs": {},
            "n_configs_hit": 0,
            "is_hard_negative": True,
            "retrieval_rank": retrieval_rank_of.get(pid),
        })
    return records


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 전건 재수집")
    parser.add_argument("--seed", type=int, default=42, help="하드 네거티브 표집 시드")
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(PERSONA_FILE)
    cache = {} if args.force else load_cache()
    todo = [r for r in records if r["persona_id"] not in cache]

    print(f"페르소나 {len(records)}건 | 캐시 {len(cache)}건 | 수집 대상 {len(todo)}건")
    print(f"그리드 {len(GRID_CONFIGS)}개 컨피그 × top-{TOP_K_PER_CONFIG}  |  rrf_k={RRF_K}")
    print("─" * 70)

    if todo:
        user_id = ensure_test_user()
        normalize = load_tag_normalizer()
        recommender = ProductRecommender()
        semaphore = asyncio.Semaphore(args.concurrency)
        done_ref = [0]
        results = await asyncio.gather(
            *(fetch_one(r, recommender, semaphore, done_ref, len(todo), user_id, normalize) for r in todo)
        )
        for persona_id, result in results:
            if result is not None:
                cache[persona_id] = result

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    missing = [r["persona_id"] for r in records if r["persona_id"] not in cache]
    if missing:
        print(f"\n미완료 {len(missing)}건 (캐시된 검색 쿼리 없음) — 건너뜀: {missing[:10]}")

    # ── 스윕 + 풀 생성 (네트워크 호출 없음) ──
    print("\n스윕 중...")
    pool_records: list[dict] = []
    grid_sizes, hard_neg_counts, total_sizes = [], [], []
    persona_by_id = {r["persona_id"]: r for r in records}

    for persona_id, cached in cache.items():
        product_tag = persona_by_id[persona_id]["product_tag"]
        recs = build_pool_records(persona_id, product_tag, cached, seed=args.seed)
        pool_records.extend(recs)
        n_hard = sum(1 for r in recs if r["is_hard_negative"])
        n_grid = len(recs) - n_hard
        grid_sizes.append(n_grid)
        hard_neg_counts.append(n_hard)
        total_sizes.append(len(recs))

    with open(POOL_FILE, "w", encoding="utf-8") as f:
        for r in pool_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("─" * 70)
    print(f"풀 생성 완료: {len(cache)}명 처리, {len(pool_records)}행 → {POOL_FILE.name}")
    if total_sizes:
        theoretical_max = len(GRID_CONFIGS) * TOP_K_PER_CONFIG
        print(
            f"페르소나별 그리드 후보 수 — 평균 {statistics.mean(grid_sizes):.1f} / "
            f"중앙값 {statistics.median(grid_sizes):.1f} / 최소 {min(grid_sizes)} / 최대 {max(grid_sizes)}  "
            f"(이론상 최대 {theoretical_max}슬롯 = {len(GRID_CONFIGS)} configs × {TOP_K_PER_CONFIG})"
        )
        print(f"압축률(그리드 후보/이론상 최대) 평균: {statistics.mean(grid_sizes) / theoretical_max * 100:.1f}%")
        print(
            f"페르소나별 하드네거티브 수 — 평균 {statistics.mean(hard_neg_counts):.1f} / "
            f"목표 {N_HARD_NEGATIVES} (채움률 {sum(hard_neg_counts) / (len(cache) * N_HARD_NEGATIVES) * 100:.1f}%)"
        )
        print(
            f"페르소나별 전체 풀 크기 — 평균 {statistics.mean(total_sizes):.1f} / "
            f"최소 {min(total_sizes)} / 최대 {max(total_sizes)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
