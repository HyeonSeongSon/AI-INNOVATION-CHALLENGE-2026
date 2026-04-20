"""
human_annotated_eval_data_set.jsonl → top5 추천 상품 JSONL 생성 스크립트

human_annotated_eval_data_set.jsonl의 각 레코드(persona_id, product_tag)를 사용해
해당 페르소나에 맞는 top5 추천 상품 ID와 RRF 스코어를 출력합니다.

사용법:
    python eval/get_eval_dataset_recommend_products.py
    python eval/get_eval_dataset_recommend_products.py --concurrency 3
    python eval/get_eval_dataset_recommend_products.py --output eval/my_output.jsonl

출력 형식 (한 줄 예시):
    {"persona_id": "PERSONA_00089", "product_tag": "크림", "top5": [{"product_id": "...", "rrf_score": 0.1234}, ...]}
"""
import asyncio
import json
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))  # app.core.* 직접 import 지원

import os
from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

from backend.app.agents.marketing_assistant.services.recommend_product import ProductRecommender

# eval 실행 중 LangSmith 트레이싱 비활성화
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

_EVAL_DIR = Path(__file__).parent
DEFAULT_INPUT  = _EVAL_DIR / "human_annotated_eval_data_set.jsonl"
DEFAULT_OUTPUT = _EVAL_DIR / "human_annotated_top5_results.jsonl"
DEFAULT_CONCURRENCY = 3

_recommender = ProductRecommender()


def load_dataset(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def run_single(
    record: dict,
    semaphore: asyncio.Semaphore,
    done_count_ref: list,
    total: int,
) -> dict | None:
    persona_id  = record["persona_id"]
    product_tag = record["product_tag"]

    async with semaphore:
        try:
            # 1. DB에서 기존 검색 쿼리 로드 (캐시된 쿼리 사용)
            queries = await _recommender.get_product_search_queries(persona_id)

            # 2. product_tag로 필터링된 1차 retrieval
            retrieval_ids = await _recommender.product_retriever(
                retrieval_query=queries["retrieval"],
                brands=None,
                sub_tags=[product_tag],
                avoided_ingredients=None,
            )

            # 3. 3차원 하이브리드 검색 + RRF → top5 (카테고리별 가중치 적용)
            recommended = await _recommender.recommend(
                queries=queries,
                retrieval_result_ids=retrieval_ids,
                top_n=5,
                product_tag=product_tag,
            )

            top5 = [
                {"product_id": p["product_id"], "rrf_score": p["rrf_score"]}
                for p in recommended
            ]

            done_count_ref[0] += 1
            print(f"[{done_count_ref[0]}/{total}] [done] {persona_id} ({product_tag}) → {[t['product_id'] for t in top5]}")

            return {
                "persona_id":  persona_id,
                "product_tag": product_tag,
                "top5":        top5,
            }

        except Exception as e:
            done_count_ref[0] += 1
            print(f"[{done_count_ref[0]}/{total}] [error] {persona_id}: {e}")
            return {
                "persona_id":  persona_id,
                "product_tag": product_tag,
                "top5":        [],
                "error":       str(e),
            }


async def main(input_path: Path, output_path: Path, concurrency: int):
    print(f"\n{'='*60}")
    print(f"human_annotated top5 추천 생성")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  동시 실행: {concurrency}")
    print(f"{'='*60}\n")

    # 이미 처리된 persona_id 수집 (재실행 시 중복 방지)
    existing_ids: set[str] = set()
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_ids.add(json.loads(line)["persona_id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
    if existing_ids:
        print(f"기존 레코드: {len(existing_ids)}개 (스킵)\n")

    all_records = load_dataset(input_path)
    targets = [r for r in all_records if r["persona_id"] not in existing_ids]
    total = len(targets)

    if total == 0:
        print("모든 레코드가 이미 처리됨. 종료.")
        return

    print(f"처리 대상: {total}개\n")

    semaphore = asyncio.Semaphore(concurrency)
    done_count_ref = [0]  # 가변 참조용 리스트

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        results = await asyncio.gather(*[
            run_single(r, semaphore, done_count_ref, total)
            for r in targets
        ])
        for result in results:
            if result is not None:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r and not r.get("error"))
    errors  = sum(1 for r in results if r and r.get("error"))

    print(f"\n{'='*60}")
    print(f"완료: 성공 {success}개, 오류 {errors}개 → {output_path}")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="human_annotated 페르소나 → top5 추천 상품 JSONL 생성")
    parser.add_argument(
        "--input", type=str, default=str(DEFAULT_INPUT),
        help=f"입력 JSONL 경로 (기본값: {DEFAULT_INPUT.name})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"출력 JSONL 경로 (기본값: {DEFAULT_OUTPUT.name})"
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"동시 실행 수 (기본값: {DEFAULT_CONCURRENCY})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        input_path=Path(args.input),
        output_path=Path(args.output),
        concurrency=args.concurrency,
    ))
