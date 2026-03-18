"""
브러쉬 카테고리 항목만 재처리하여 product_data_structured_beauty_tool.jsonl 업데이트
- 프롬프트에 value 필드 가이드를 추가한 후 실행
- 브러쉬 항목만 LLM 재처리 후 원본 파일의 해당 항목을 교체
"""
import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from document_beauty_tool_prompt import build_beauty_device_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_beauty_tool.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _BEAUTY_TOOL_CATEGORIES: list[str] = json.load(_f)["category_type"]["뷰티 툴"]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

BRUSH_TAGS = {"얼굴브러쉬", "눈브러쉬", "입술브러쉬", "브러쉬세트", "치크브러쉬"}


def build_prompt(product: dict) -> str:
    document = product.get("문서", "")
    return build_beauty_device_category_product_prompt("brush", document, _BEAUTY_TOOL_CATEGORIES)


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
        product_id = product.get("product_id", "?")
        name = product.get("상품명", "?")[:30]
        print(f"[{idx}/{total}] {product_id} {name} 처리 중...")
        prompt = build_prompt(product)
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            structured = parse_llm_json(response.content)
            print(f"[{idx}/{total}] {product_id} 완료 | value={structured.get('value', [])}")
        except Exception as e:
            structured = product.get("structured", {})  # 실패 시 기존 값 유지
            print(f"[{idx}/{total}] {product_id} 실패(기존값 유지) — {e}")
        return {**product, "structured": structured}


async def main():
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        all_products = [json.loads(line) for line in f if line.strip()]

    brush_indices = [(i, p) for i, p in enumerate(all_products) if p.get("태그") in BRUSH_TAGS]
    total = len(brush_indices)
    print(f"브러쉬 카테고리 {total}개 재처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(p, semaphore, idx + 1, total)
        for idx, (_, p) in enumerate(brush_indices)
    ]
    results = await asyncio.gather(*tasks)

    # 원본 리스트에서 브러쉬 항목만 교체
    for (original_idx, _), updated in zip(brush_indices, results):
        all_products[original_idx] = updated

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for p in all_products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r.get("structured", {}).get("value"))
    print(f"\n완료: {success}/{total}개에서 value 추출 성공 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
