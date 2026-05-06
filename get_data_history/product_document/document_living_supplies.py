import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from document_living_supplies_prompt import build_daily_goods_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_FILE  = Path(__file__).parent.parent.parent / "data" / "product_data.jsonl"
OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "v2_product_data_structured_living_supplies.jsonl"
CONCURRENCY = 10  # 동시 LLM 호출 수

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "category.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _living_raw = json.load(_f)["categories"]["생활도구"]
    _LIVING_CATEGORIES: list[str] = [v for vals in _living_raw.values() for v in vals]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 태그 → 생활도구 그룹 매핑
TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "생활가전": "home_appliance",
    "용기&수저": "tableware",
}


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    document = product.get("문서", "")
    extra_category = TAG_TO_EXTRA_CATEGORY[tag]
    return build_daily_goods_product_prompt(extra_category, document, _LIVING_CATEGORIES)


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
            response = await llm.ainvoke([HumanMessage(content=prompt)])
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

    living_products = [p for p in products if p.get("태그") in TAG_TO_EXTRA_CATEGORY]
    total = len(living_products)
    print(f"생활도구 {total}/{len(products)}개 처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(p, semaphore, i + 1, total)
        for i, p in enumerate(living_products)
    ]
    results = await asyncio.gather(*tasks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r.get("structured"))
    print(f"\n완료: {success}/{total} 성공 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
