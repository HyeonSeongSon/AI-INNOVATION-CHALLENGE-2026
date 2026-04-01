"""
헤어 데이터 대상 항목만 재처리
- value 빈값 3건: 인리치 본딩 케어 샴푸, 인핸싱 실키 컬러 샴푸, 인핸싱 실키 오일
- 완전 붕괴(문서 오염) 1건: 리밸런싱 모이스처 샴푸 → 상품명 기반 fallback 사용
"""
import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from get_data_history.product_document.document_hair_prompt import build_hair_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage


OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "v2_product_data_structured_hair.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "category.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _hair_raw = json.load(_f)["categories"]["헤어"]
    _HAIR_CATEGORIES: list[str] = [v for vals in _hair_raw.values() for v in vals]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "세정": "hair_cleansing",
    "모발케어": "hair_treatment",
    "두피케어": "scalp_care",
    "스타일링": "hair_styling_", 
    "헤어컬러": "hair_color",
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

TARGET_PRODUCT_IDS = {
    "A20251200053",
    "A20251200061",
    "A20251200062"
}

# 문서 오염으로 상품명+한줄소개 기반 fallback 사용할 product_id 목록
FALLBACK_PRODUCT_IDS = {"A20251200410"}


def build_fallback_document(product: dict) -> str:
    return (
        f"브랜드: {product.get('브랜드', '')}\n"
        f"상품명: {product.get('상품명', '')}\n"
        f"카테고리: {product.get('태그', '')}\n"
        f"상품 소개: {product.get('한줄소개', '')}"
    )


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    pid = product.get("product_id", "")
    document = build_fallback_document(product) if pid in FALLBACK_PRODUCT_IDS else product.get("문서", "")
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag)
    return build_hair_category_product_prompt(extra_category, document, _HAIR_CATEGORIES)


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
        pid = product.get("product_id", "?")
        fallback = pid in FALLBACK_PRODUCT_IDS
        print(f"[{idx}/{total}] [{tag}] {name[:30]} {'(fallback)' if fallback else ''} 처리 중...")
        prompt = build_prompt(product)
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            structured = parse_llm_json(response.content)
            val = structured.get("value", [])
            print(f"[{idx}/{total}] 완료 | value={val[:3]}")
        except Exception as e:
            structured = product.get("structured", {})
            print(f"[{idx}/{total}] 실패(기존값 유지) — {e}")
        return {**product, "structured": structured}


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
