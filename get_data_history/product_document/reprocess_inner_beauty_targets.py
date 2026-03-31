"""
이너뷰티 데이터 대상 항목 재처리
- structured 빈값 1건 (400 에러, fallback): A20251200829
"""
import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from get_data_history.product_document.document_inner_beauty_prompt import build_inner_beauty_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "v2_product_data_structured_inner_beauty.jsonl"
CONCURRENCY = 5
MAX_RETRIES = 3

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "category.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _inner_beauty_raw = json.load(_f)["categories"]["이너뷰티"]
    _INNER_BEAUTY_CATEGORIES: list[str] = [v for vals in _inner_beauty_raw.values() for v in vals]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 태그 → 이너뷰티 그룹 매핑
TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "기능성이너뷰티": "functional_subtags",
    "이너뷰티푸드": "food_subtags"
}

TARGET_PRODUCT_IDS = {"A20251200829"}


def build_fallback_document(product: dict) -> str:
    return (
        f"브랜드: {product.get('브랜드', '')}\n"
        f"상품명: {product.get('상품명', '')}\n"
        f"카테고리: {product.get('태그', '')}\n"
        f"상품 소개: {product.get('한줄소개', '')}"
    )


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    document = build_fallback_document(product)
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag, "inner_beauty")
    return build_inner_beauty_category_product_prompt(extra_category, document, _INNER_BEAUTY_CATEGORIES)


def parse_llm_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


async def process_product(product: dict, semaphore: asyncio.Semaphore, idx: int, total: int) -> dict:
    async with semaphore:
        name = product.get("상품명", "?")
        tag = product.get("태그", "?")
        print(f"[{idx}/{total}] [{tag}] {name[:35]} (fallback) 처리 중...")
        prompt = build_prompt(product)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await llm.ainvoke([HumanMessage(content=prompt)])
                structured = parse_llm_json(response.content)
                val = structured.get("value", [])
                print(f"[{idx}/{total}] 완료 (시도 {attempt}) | value={val[:3]}")
                return {**product, "structured": structured}
            except Exception as e:
                print(f"[{idx}/{total}] 시도 {attempt}/{MAX_RETRIES} 실패 — {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1)
        print(f"[{idx}/{total}] 모든 재시도 실패 — 기존값 유지")
        return product


async def main():
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        all_products = [json.loads(line) for line in f if line.strip()]

    target_indices = [
        (i, p) for i, p in enumerate(all_products)
        if p.get("product_id") in TARGET_PRODUCT_IDS
    ]
    total = len(target_indices)
    print(f"재처리 대상 {total}개 (동시 {CONCURRENCY}개)")
    for _, p in target_indices:
        print(f"  [{p.get('태그')}] {p.get('상품명')}")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(p, semaphore, idx + 1, total)
        for idx, (_, p) in enumerate(target_indices)
    ]
    results = await asyncio.gather(*tasks)

    for (original_idx, _), updated in zip(target_indices, results):
        all_products[original_idx] = updated

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for p in all_products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"\n완료 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
