"""
이너뷰티 데이터 대상 항목 재처리
- 스킨케어로 잘못 구조화 1건 (fallback): A20251200264 — 슈퍼콜라겐 프리미엄(28일)
- concern/ingredient 빈값 1건 (기존 문서): A20251200245 — 메타그린 칼로리컷 젤리
- concern/ingredient/nutrients 전부 빈값 1건 (fallback): A20251200263 — 명작수 골드(100일)
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

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_inner_beauty_v.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _INNER_BEAUTY_CATEGORIES: list[str] = json.load(_f)["category_type"]["이너뷰티"]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "이너뷰티":     "inner_beauty",
    "슬리밍":       "inner_beauty",
    "영양보충":     "inner_beauty",
    "건강기능식품": "inner_beauty",
    "브렌딩티/차":  "tea",
    "차세트":       "tea",
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 스킨케어로 잘못 구조화 or concern/ingredient 전부 빈값 → fallback 사용
FALLBACK_PRODUCT_IDS = {
    "A20251200264",  # 슈퍼콜라겐 프리미엄(28일) — 스킨케어로 잘못 구조화
    "A20251200263",  # 명작수 골드(100일) — concern/ingredient/nutrients 전부 빈값
}

TARGET_PRODUCT_IDS = FALLBACK_PRODUCT_IDS | {
    "A20251200245",  # 메타그린 칼로리컷 젤리 — concern/ingredient 빈값 (기존 문서 재처리)
}


def build_fallback_document(product: dict) -> str:
    return (
        f"브랜드: {product.get('브랜드', '')}\n"
        f"상품명: {product.get('상품명', '')}\n"
        f"카테고리: {product.get('태그', '')}\n"
        f"상품 소개: {product.get('한줄소개', '')}"
    )


def build_prompt(product: dict) -> str:
    pid = product.get("product_id", "")
    tag = product.get("태그", "")
    document = build_fallback_document(product) if pid in FALLBACK_PRODUCT_IDS else product.get("문서", "")
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
        pid = product.get("product_id", "?")
        fallback = pid in FALLBACK_PRODUCT_IDS
        print(f"[{idx}/{total}] [{tag}] {name[:35]} {'(fallback)' if fallback else ''} 처리 중...")
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
        pid = p.get("product_id")
        flag = "(fallback)" if pid in FALLBACK_PRODUCT_IDS else "(기존 문서)"
        print(f"  [{p.get('태그')}] {p.get('상품명')} {flag}")

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
