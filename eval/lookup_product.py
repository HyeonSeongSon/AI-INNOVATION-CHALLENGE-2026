"""
상품 ID로 태그와 문서 내용을 조회하는 스크립트

사용법:
    python lookup_product.py <product_id>
    python lookup_product.py A20251200001
"""

import io
import json
import sys
from pathlib import Path

# Windows 콘솔 CP949 인코딩 문제 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DATA_PATH = Path(__file__).parent.parent / "data" / "product_data_251231.jsonl"


def load_product(product_id: str) -> dict | None:
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            product = json.loads(line)
            if product.get("product_id") == product_id:
                return product
    return None


def print_product(product: dict):
    print(f"{'='*60}")
    print(f"상품 ID   : {product.get('product_id')}")
    print(f"브랜드    : {product.get('브랜드')}")
    print(f"상품명    : {product.get('상품명')}")
    print(f"{'='*60}")
    print(f"[태그]")
    print(f"  카테고리 태그 : {product.get('태그')}")
    persona = product.get("페르소나태그", {})
    if persona:
        print(f"  피부타입      : {persona.get('피부타입')}")
        print(f"  고민키워드    : {persona.get('고민키워드')}")
        print(f"  선호성분      : {persona.get('선호성분')}")
        print(f"  기피성분      : {persona.get('기피성분')}")
        print(f"  선호향        : {persona.get('선호향')}")
        print(f"  가치관        : {persona.get('가치관')}")
        print(f"  전용제품      : {persona.get('전용제품')}")
    print(f"\n[문서]\n")
    print(product.get("문서", "(문서 없음)"))
    print(f"\n{'='*60}")


def main():
    if len(sys.argv) < 2:
        product_id = input("상품 ID를 입력하세요: ").strip()
    else:
        product_id = sys.argv[1].strip()

    if not product_id:
        print("상품 ID가 입력되지 않았습니다.")
        sys.exit(1)

    print(f"'{product_id}' 검색 중...", file=sys.stderr)
    product = load_product(product_id)

    if product is None:
        print(f"상품 ID '{product_id}'를 찾을 수 없습니다.")
        sys.exit(1)

    print_product(product)


if __name__ == "__main__":
    main()
