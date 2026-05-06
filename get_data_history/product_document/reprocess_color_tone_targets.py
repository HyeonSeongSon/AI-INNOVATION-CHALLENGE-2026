"""
색조 데이터 대상 항목만 재처리
- 아이라이너 ingredient 누락 2건: [세잔느] 드로잉 더블 아이라이너, [피카소꼴레지오니] 401 아이라이너
- value 재처리 가능 4건: 디어 달링 워터젤 틴트, 에어쿠션 5.5세대 커버, 무드업 음영 아이팔레트, [디즈니에디션] 블러리 치크
- 아이라이너 value 빈값 1건: 프루프 10 젤 방수 펜슬
"""
import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from get_data_history.product_document.document_color_prompts import build_color_tone_prompts
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_color_tone.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _COLOR_CATEGORIES: list[str] = json.load(_f)["category_type"]["색조"]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "파운데이션": "base_makeup", "BB&CC크림": "base_makeup",
    "쿠션": "base_makeup", "컨실러": "base_makeup",
    "파우더": "base_makeup", "프라이머&베이스": "base_makeup",
    "립스틱": "lip_makeup", "립글로스": "lip_makeup",
    "립틴트": "lip_makeup", "립케어&립밤": "lip_makeup",
    "마스카라": "eye_makeup", "아이라이너": "eye_makeup",
    "아이브로우": "eye_makeup", "아이래쉬": "eye_makeup",
    "아이프라이머": "eye_makeup", "아이섀도우": "eye_makeup",
    "브러셔": "cheek", "브론져": "cheek", "하이라이터": "cheek",
    "키트&팔레트": "palette",
}

# 재처리 대상 product_id
TARGET_PRODUCT_IDS = {
    # 아이라이너 ingredient 누락
    "[세잔느] 드로잉 더블 아이라이너",
    "[피카소꼴레지오니] 401 아이라이너",
    # value 재처리
    "디어 달링 워터젤 틴트",
    "에어쿠션 5.5세대 커버 SPF50/PA+++ 15g",
    "무드업 음영 아이팔레트 7g",
    "[디즈니에디션] 블러리 치크",
    "프루프 10 젤 방수 펜슬 0.3 g",
}


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    document = product.get("문서", "")
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag)
    return build_color_tone_prompts(extra_category, document, _COLOR_CATEGORIES)


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
        print(f"[{idx}/{total}] [{tag}] {name[:35]} 처리 중...")
        prompt = build_prompt(product)
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            structured = parse_llm_json(response.content)
            ing = structured.get("ingredient", [])
            val = structured.get("value", [])
            print(f"[{idx}/{total}] 완료 | ingredient={ing[:2]} | value={val[:2]}")
        except Exception as e:
            structured = product.get("structured", {})
            print(f"[{idx}/{total}] 실패(기존값 유지) — {e}")
        return {**product, "structured": structured}


async def main():
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        all_products = [json.loads(line) for line in f if line.strip()]

    target_indices = [
        (i, p) for i, p in enumerate(all_products)
        if p.get("상품명") in TARGET_PRODUCT_IDS
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
