"""
실패한 product_id를 재처리하는 스크립트

사용법:
  # 모든 failed_*.jsonl 파일 자동 감지 후 재처리
  python run_retry_failed.py

  # 특정 카테고리의 실패 파일만
  python run_retry_failed.py --category hair

  # 특정 product_id 직접 지정 (카테고리 포함)
  python run_retry_failed.py --ids A20251200410:hair A20251200411:fragrance_body

동작:
  1. failed_*.jsonl 에서 실패 목록 읽기 (또는 --ids 직접 지정)
  2. v2 입력 파일에서 해당 product 로드
  3. LLM 재처리 (최대 2회 시도)
  4. 성공 시 v3 출력 파일에 추가 + failed 파일에서 해당 항목 제거
  5. 최종 실패 시 failed 파일에 유지
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from get_data_history.product_document.v3.rewrite_semantic_fields_prompt import (
    build_rewrite_semantic_fields_prompt,
)
from get_data_history.product_document.v3.run_rewrite_semantic_fields import (
    _call_llm_and_validate,
    rewrite_product,
    CONCURRENCY,
    DATA_DIR,
    CATEGORIES,
)

# ──────────────────────────────────────────────
# 실패 목록 로드
# ──────────────────────────────────────────────

def load_failed_ids(categories: list[str] | None = None) -> dict[str, list[str]]:
    """failed_*.jsonl 에서 {category: [product_id, ...]} 반환"""
    result: dict[str, list[str]] = defaultdict(list)

    target_cats = categories if categories else CATEGORIES
    for cat in target_cats:
        failed_file = DATA_DIR / f"failed_{cat}.jsonl"
        if not failed_file.exists():
            continue
        with open(failed_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    result[item["category"]].append(item["product_id"])
                except Exception:
                    pass

    return dict(result)


def load_products_by_ids(category: str, product_ids: set[str]) -> list[dict]:
    """v2 입력 파일에서 지정 product_id만 로드"""
    input_file = DATA_DIR / f"v2_product_data_structured_{category}.jsonl"
    if not input_file.exists():
        print(f"[WARN] {input_file.name} 없음")
        return []

    products = []
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
                if p.get("product_id") in product_ids:
                    products.append(p)
            except Exception:
                pass

    found_ids = {p["product_id"] for p in products}
    missing = product_ids - found_ids
    if missing:
        print(f"[WARN] [{category}] v2에서 찾지 못한 ID: {missing}")

    return products


# ──────────────────────────────────────────────
# failed 파일 갱신 (성공한 ID 제거)
# ──────────────────────────────────────────────

def remove_from_failed_file(category: str, succeeded_ids: set[str]) -> None:
    """성공한 product_id를 failed_*.jsonl 에서 제거"""
    failed_file = DATA_DIR / f"failed_{category}.jsonl"
    if not failed_file.exists():
        return

    remaining = []
    with open(failed_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if item.get("product_id") not in succeeded_ids:
                    remaining.append(line)
            except Exception:
                remaining.append(line)

    with open(failed_file, "w", encoding="utf-8") as f:
        for line in remaining:
            f.write(line + "\n")

    print(f"[{category}] failed 파일에서 {len(succeeded_ids)}건 제거 → {failed_file.name}")


# ──────────────────────────────────────────────
# 카테고리별 재처리
# ──────────────────────────────────────────────

async def retry_category(category: str, product_ids: list[str]) -> None:
    if not product_ids:
        return

    print(f"\n[{category}] 재처리 대상: {len(product_ids)}건")

    products = load_products_by_ids(category, set(product_ids))
    if not products:
        print(f"[{category}] 재처리할 상품 없음")
        return

    output_file = DATA_DIR / f"v3_product_data_rewritten_{category}.jsonl"

    semaphore = asyncio.Semaphore(CONCURRENCY)
    total = len(products)
    tasks = [
        rewrite_product(p, semaphore, i + 1, total)
        for i, p in enumerate(products)
    ]
    results = await asyncio.gather(*tasks)

    succeeded = [(r, ok) for r, ok in results if ok]
    failed    = [(r, ok) for r, ok in results if not ok]

    # 성공 결과를 v3 출력 파일에 추가
    if succeeded:
        with open(output_file, "a", encoding="utf-8") as f:
            for r, _ in succeeded:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{category}] 성공 {len(succeeded)}/{total}건 → {output_file.name}")

    # 성공한 ID를 failed 파일에서 제거
    succeeded_ids = {r.get("product_id") for r, _ in succeeded}
    remove_from_failed_file(category, succeeded_ids)

    # 여전히 실패한 항목은 failed 파일에 유지
    if failed:
        failed_file = DATA_DIR / f"failed_{category}.jsonl"
        still_failed_ids = {r.get("product_id") for r, _ in failed}
        print(f"[{category}] 여전히 실패 {len(failed)}건: {still_failed_ids} → {failed_file.name}")


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

async def main(failed_map: dict[str, list[str]]) -> None:
    if not failed_map:
        print("재처리할 실패 항목이 없습니다.")
        return

    total_count = sum(len(ids) for ids in failed_map.values())
    print(f"총 {total_count}건 재처리 시작 (카테고리: {list(failed_map.keys())})")

    for category, product_ids in failed_map.items():
        await retry_category(category, product_ids)

    print("\n재처리 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="실패한 product_id 재처리")
    parser.add_argument(
        "--category", "-c",
        nargs="+",
        help="재처리할 카테고리 (미지정 시 전체 failed_*.jsonl 자동 감지)",
    )
    parser.add_argument(
        "--ids", "-i",
        nargs="+",
        metavar="PRODUCT_ID:CATEGORY",
        help="직접 지정: product_id:category 형식 (예: A20251200410:hair)",
    )
    args = parser.parse_args()

    if args.ids:
        # 직접 지정 모드
        failed_map: dict[str, list[str]] = defaultdict(list)
        for item in args.ids:
            if ":" not in item:
                print(f"[ERROR] 형식 오류: '{item}' — product_id:category 형식이어야 합니다")
                sys.exit(1)
            pid, cat = item.rsplit(":", 1)
            failed_map[cat].append(pid)
        failed_map = dict(failed_map)
    else:
        # failed_*.jsonl 자동 감지 모드
        failed_map = load_failed_ids(args.category)

    asyncio.run(main(failed_map))
