import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from get_data_history.product_document.document_color_prompts import build_color_tone_prompts
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_FILE  = Path(__file__).parent.parent.parent / "data" / "product_data_251231.jsonl"
OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_color_tone.jsonl"
CONCURRENCY = 10  # 동시 LLM 호출 수

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _COLOR_CATEGORIES: list[str] = json.load(_f)["category_type"]["색조"]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 태그 → 색조 그룹 매핑
TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    # 베이스 메이크업
    "파운데이션":       "base_makeup",
    "BB&CC크림":        "base_makeup",
    "쿠션":             "base_makeup",
    "컨실러":           "base_makeup",
    "파우더":           "base_makeup",
    "프라이머&베이스":  "base_makeup",
    # 립 메이크업
    "립스틱":           "lip_makeup",
    "립글로스":         "lip_makeup",
    "립틴트":           "lip_makeup",
    "립케어&립밤":      "lip_makeup",
    # 아이 메이크업
    "마스카라":         "eye_makeup",
    "아이라이너":       "eye_makeup",
    "아이브로우":       "eye_makeup",
    "아이래쉬":         "eye_makeup",
    "아이프라이머":     "eye_makeup",
    "아이섀도우":       "eye_makeup",
    # 치크/쉐딩
    "브러셔":           "cheek",
    "브론져":           "cheek",
    "하이라이터":       "cheek",
    # 묶음
    "키트&팔레트":      "palette",
}


def build_prompt(product: dict) -> str:
    tag      = product.get("태그", "")
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


async def process_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    async with semaphore:
        product_id = product.get("product_id", "?")
        print(f"[{idx}/{total}] {product_id} 처리 중...")
        prompt = build_prompt(product)
        try:
            response   = await llm.ainvoke([HumanMessage(content=prompt)])
            structured = parse_llm_json(response.content)
            print(f"[{idx}/{total}] {product_id} 완료")
        except Exception as e:
            structured = {}
            print(f"[{idx}/{total}] {product_id} 실패 — {e}")

        return {**product, "structured": structured}


async def main():
    products: list[dict] = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    color_products = [p for p in products if p.get("태그") in TAG_TO_EXTRA_CATEGORY]
    total = len(color_products)
    print(f"색조 {total}/{len(products)}개 처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(p, semaphore, i + 1, total)
        for i, p in enumerate(color_products)
    ]
    results = await asyncio.gather(*tasks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r.get("structured"))
    print(f"\n완료: {success}/{total} 성공 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
