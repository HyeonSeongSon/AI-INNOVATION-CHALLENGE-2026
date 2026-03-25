"""
RAG 추천 시스템 평가 스크립트

사용법:
    python eval/run_eval.py [--input PATH] [--top_n N] [--concurrency N] [--output PATH]

동작:
    1. synthetic_eval_dataset.jsonl 로드
    2. 각 레코드의 persona_info → 검색 쿼리 생성 (LLM)
    3. 1차 retrieval (top 100, 필터 없음) → Retrieval Hit@100 측정
    4. 3차원 RRF → 상위 top_n 추천 → Hit@N / Recall@N / Precision@N / MRR 측정
    5. 카테고리별 + 전체 결과 출력 및 JSONL 저장
"""
import asyncio
import sys
import json
import argparse
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (백엔드 패키지 import 가능하도록)
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

from backend.app.agents.marketing_assistant.services.generate_product_search_query_from_persona import (
    generate_product_search_query_from_persona,
)
from backend.app.agents.marketing_assistant.services.recommend_product import ProductRecommender
from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

_recommender = ProductRecommender()


def load_eval_dataset(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def run_single(
    record: dict,
    llm,
    semaphore: asyncio.Semaphore,
    top_n: int,
    use_category_filter: bool = False,
) -> dict:
    """단일 레코드 평가 (쿼리 생성 → retrieval → RRF → 메트릭 계산)"""
    eval_id = record["eval_id"]
    source_product_id = record["source_product_id"]
    persona_info = record["persona_info"]
    ground_truth_ids = set(record["ground_truth"]["product_ids"])

    # 카테고리 필터: source_product_tag를 사용해 실제 사용 환경 재현
    product_tag = (
        [record["source_product_tag"]] if use_category_filter and record.get("source_product_tag") else None
    )

    async with semaphore:
        try:
            # 1. 검색 쿼리 생성 (persona_info 직접 사용, DB 조회 없음)
            raw_queries = await generate_product_search_query_from_persona(llm, persona_info)
            queries = {
                "user_need_query": raw_queries["need"],
                "user_preference_query": raw_queries["preference"],
                "retrieval": raw_queries["retrieval"],
                "persona": raw_queries["persona"],
            }

            # 2. 1차 retrieval
            retrieval_ids = await _recommender.product_retriever(
                retrieval_query=queries["retrieval"],
                brands=None,
                product_tag=product_tag,
                avoided_ingredients=None,
            )

            # Retrieval 단계 메트릭 (1차 후보에 ground truth 포함 여부)
            retrieval_hit = source_product_id in retrieval_ids
            retrieval_recall = (
                len(ground_truth_ids & set(retrieval_ids)) / len(ground_truth_ids)
                if ground_truth_ids else 0.0
            )

            # 3. 3차원 하이브리드 검색 + RRF → 최종 top_n 추천
            recommended = await _recommender.recommend(queries, retrieval_ids, top_n=top_n)
            top_ids = [p["product_id"] for p in recommended]

            # 4. 최종 추천 단계 메트릭
            hit = source_product_id in top_ids
            precision_at_n = len(ground_truth_ids & set(top_ids)) / top_n
            recall_at_n = (
                len(ground_truth_ids & set(top_ids)) / len(ground_truth_ids)
                if ground_truth_ids else 0.0
            )
            mrr = 0.0
            for rank, pid in enumerate(top_ids, start=1):
                if pid in ground_truth_ids:
                    mrr = 1.0 / rank
                    break

            print(
                f"[done] {eval_id} ({record.get('source_product_category', '')}) "
                f"| retrieval_hit={retrieval_hit} hit@{top_n}={hit} mrr={mrr:.3f}"
            )

            return {
                "eval_id": eval_id,
                "source_product_id": source_product_id,
                "category": record.get("source_product_category", ""),
                "category_filter_applied": product_tag,
                "queries": queries,
                "retrieval_count": len(retrieval_ids),
                "retrieval_hit": retrieval_hit,
                "retrieval_recall": retrieval_recall,
                "top_ids": top_ids,
                "hit": hit,
                "precision_at_n": precision_at_n,
                "recall_at_n": recall_at_n,
                "mrr": mrr,
                "error": None,
            }

        except Exception as e:
            print(f"[error] {eval_id}: {e}")
            return {
                "eval_id": eval_id,
                "source_product_id": source_product_id,
                "category": record.get("source_product_category", ""),
                "retrieval_hit": False,
                "retrieval_recall": 0.0,
                "retrieval_count": 0,
                "top_ids": [],
                "hit": False,
                "precision_at_n": 0.0,
                "recall_at_n": 0.0,
                "mrr": 0.0,
                "error": str(e),
            }


async def main(input_path: Path, top_n: int, concurrency: int, output_path: Path, use_category_filter: bool = False):
    print(f"\n{'='*72}")
    print(f"RAG 추천 평가: {input_path.name}")
    print(f"  top_n={top_n}  concurrency={concurrency}  model={settings.chatgpt_model_name}")
    print(f"  category_filter={'ON (source_product_tag 적용)' if use_category_filter else 'OFF (전체 상품 대상)'}")
    print(f"{'='*72}\n")

    records = load_eval_dataset(input_path)
    print(f"총 {len(records)}개 레코드 로드\n")

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*[run_single(r, llm, semaphore, top_n, use_category_filter) for r in records])

    valid = [r for r in results if r["error"] is None]
    errors = [r for r in results if r["error"] is not None]

    # 카테고리별 집계
    by_category: dict[str, list[dict]] = {}
    for r in valid:
        by_category.setdefault(r["category"], []).append(r)

    # 결과 출력
    col = f"{'카테고리':<20} {'N':>4} {'Ret.Hit@100':>12} {'Hit@'+str(top_n):>8} {'Recall@'+str(top_n):>10} {'Prec@'+str(top_n):>8} {'MRR':>8}"
    sep = "-" * 74
    print(f"\n{'='*74}")
    print(f"평가 결과 (top_{top_n})")
    print(f"{'='*74}")
    print(col)
    print(sep)

    all_rh, all_h, all_r, all_p, all_m = [], [], [], [], []
    for cat, cat_results in sorted(by_category.items()):
        n = len(cat_results)
        rh = sum(r["retrieval_hit"] for r in cat_results) / n
        h  = sum(r["hit"] for r in cat_results) / n
        r_ = sum(r["recall_at_n"] for r in cat_results) / n
        p  = sum(r["precision_at_n"] for r in cat_results) / n
        m  = sum(r["mrr"] for r in cat_results) / n
        print(f"{cat:<20} {n:>4} {rh:>12.3f} {h:>8.3f} {r_:>10.3f} {p:>8.3f} {m:>8.3f}")
        all_rh += [r["retrieval_hit"] for r in cat_results]
        all_h  += [r["hit"] for r in cat_results]
        all_r  += [r["recall_at_n"] for r in cat_results]
        all_p  += [r["precision_at_n"] for r in cat_results]
        all_m  += [r["mrr"] for r in cat_results]

    n_total = len(valid)
    print("=" * 74)
    if n_total:
        print(
            f"{'전체 평균':<20} {n_total:>4} "
            f"{sum(all_rh)/n_total:>12.3f} "
            f"{sum(all_h)/n_total:>8.3f} "
            f"{sum(all_r)/n_total:>10.3f} "
            f"{sum(all_p)/n_total:>8.3f} "
            f"{sum(all_m)/n_total:>8.3f}"
        )

    if errors:
        print(f"\n오류 {len(errors)}건:")
        for e in errors:
            print(f"  - {e['eval_id']}: {e['error']}")

    print(f"{'='*74}\n")

    # 상세 결과 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"상세 결과 저장 → {output_path}")


def parse_args():
    _EVAL_DIR = Path(__file__).parent
    parser = argparse.ArgumentParser(description="RAG 추천 시스템 평가")
    parser.add_argument(
        "--input", default=str(_EVAL_DIR / "synthetic_eval_dataset.jsonl"),
        help="평가 데이터셋 경로"
    )
    parser.add_argument("--top_n", type=int, default=3, help="최종 추천 상품 수 (기본값: 3)")
    parser.add_argument("--concurrency", type=int, default=3, help="동시 실행 수 (기본값: 3)")
    parser.add_argument(
        "--output", default=str(_EVAL_DIR / "eval_results.jsonl"),
        help="결과 저장 경로"
    )
    parser.add_argument(
        "--use_category_filter", action="store_true",
        help="source_product_tag로 카테고리 필터 적용 (실제 사용 환경 재현)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        input_path=Path(args.input),
        top_n=args.top_n,
        concurrency=args.concurrency,
        output_path=Path(args.output),
        use_category_filter=args.use_category_filter,
    ))
