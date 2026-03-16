import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from generate_product_document_prompts import (
    build_skin_care_category_product_prompt,
    build_generate_base_product_document_prompt,
)
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_FILE  = Path(__file__).parent.parent.parent / "data" / "product_data_251231.jsonl"
OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_skincare.jsonl"
CONCURRENCY = 10  # 동시 LLM 호출 수

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _SKINCARE_CATEGORIES: list[str] = json.load(_f)["category_type"]["스킨케어"]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 태그 → 스킨케어 세부 카테고리 매핑
TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    # 클렌징
    "클렌징 오일":      "cleansing",
    "클렌징 워터":      "cleansing",
    "클렌징 폼":        "cleansing",
    "메이크업 리무버":  "cleansing",
    "클렌징 티슈":      "cleansing",
    # 기초케어
    "스킨&토너":        "base_care",
    "에센스&세럼":      "base_care",
    "앰플":             "base_care",
    "로션&에멀젼":      "base_care",
    "크림":             "base_care",
    "미스트":           "base_care",
    "페이스 오일":      "base_care",
    # 특수케어
    "마스크&팩":        "special_care",
    "아이&넥":          "special_care",
    "코팩":             "special_care",
    "필링&스크럽":      "special_care",
    # 선케어
    "선케어":           "sun_care",
    "선크림":           "sun_care",
    "선스틱":           "sun_care",
    "선블럭":           "sun_care",
    # 스킨케어 세트
    "스킨케어세트":     "skincare_set",
}


# ingredient 추상화 감지 패턴
_ABSTRACT_INGREDIENT_NAMES = {
    # 기존 패턴
    "오일 성분", "에센스 오일", "저자극 성분", "유효성분", "유효 성분",
    "보습 성분", "오일계 성분", "성분", "유효 성분군", "핵심 성분",
    # 신규 패턴 (마케팅 조어 기반 추상 표현)
    "발효 성분", "수분 광물", "수분 미네랄", "진정 광물", "고분자 보습 오일",
    "안티에이징 성분", "수분 성분", "진정 성분", "미네랄 성분",
}

# 문장형 마케팅 문구 감지용 키워드 (성분명이 아닌 문장 표현 탐지)
_ABSTRACT_INGREDIENT_KEYWORDS = {"성분들", "찾아낸", "최고의"}


def _ingredient_quality(structured: dict) -> str:
    """ingredient 추출 품질 평가: ok / low / empty"""
    ingredients = structured.get("ingredient", [])
    if not ingredients:
        return "empty"
    names = {i.split(" (")[0].strip() for i in ingredients}
    if names & _ABSTRACT_INGREDIENT_NAMES:
        return "low"
    if any(kw in name for name in names for kw in _ABSTRACT_INGREDIENT_KEYWORDS):
        return "low"
    return "ok"


def build_prompt(product: dict) -> str:
    tag      = product.get("태그", "")
    document = product.get("문서", "")
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag)
    if extra_category:
        return build_skin_care_category_product_prompt(extra_category, document, _SKINCARE_CATEGORIES)
    return build_generate_base_product_document_prompt(document, _SKINCARE_CATEGORIES)


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
            response  = await llm.ainvoke([HumanMessage(content=prompt)])
            structured = parse_llm_json(response.content)
            print(f"[{idx}/{total}] {product_id} 완료")
        except Exception as e:
            structured = {}
            print(f"[{idx}/{total}] {product_id} 실패 — {e}")

        if structured:
            structured["ingredient_quality"] = _ingredient_quality(structured)

        return {**product, "structured": structured}


async def main():
    products: list[dict] = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    skincare_products = [p for p in products if p.get("태그") in TAG_TO_EXTRA_CATEGORY]
    total = len(skincare_products)
    print(f"스킨케어 {total}/{len(products)}개 처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(p, semaphore, i + 1, total)
        for i, p in enumerate(skincare_products)
    ]
    results = await asyncio.gather(*tasks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r.get("structured"))
    print(f"\n완료: {success}/{total} 성공 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
