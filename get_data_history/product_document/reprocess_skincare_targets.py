"""
스킨케어 데이터 대상 항목 재처리
- LLM 오염 문서 1건 (fallback): A20251200064 — 풋 테라피 케어 SET
- value==[] 8건 (기존 문서 재처리): A20251200045, A20251200509, A20251200516,
  A20251200520, A20251200523, A20251200763, A20251200783, A20251200810
- 판매처 정보 value 6건 (fallback): A20251200634, A20251200638, A20251200641,
  A20251200643, A20251200650, A20251200652
"""
import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from get_data_history.product_document.generate_product_document_prompts import (
    build_skin_care_category_product_prompt,
)
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_skincare.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _SKINCARE_CATEGORIES: list[str] = json.load(_f)["category_type"]["스킨케어"]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "클렌징 오일":      "cleansing",
    "클렌징 워터":      "cleansing",
    "클렌징 폼":        "cleansing",
    "메이크업 리무버":  "cleansing",
    "클렌징 티슈":      "cleansing",
    "스킨&토너":        "base_care",
    "에센스&세럼":      "base_care",
    "앰플":             "base_care",
    "로션&에멀젼":      "base_care",
    "크림":             "base_care",
    "미스트":           "base_care",
    "페이스 오일":      "base_care",
    "마스크&팩":        "special_care",
    "아이&넥":          "special_care",
    "코팩":             "special_care",
    "필링&스크럽":      "special_care",
    "선케어":           "sun_care",
    "선크림":           "sun_care",
    "선스틱":           "sun_care",
    "선블럭":           "sun_care",
    "스킨케어세트":     "skincare_set",
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)

# 문서 오염 또는 판매처 정보 → fallback 사용할 product_id 목록
FALLBACK_PRODUCT_IDS = {
    "A20251200064",  # 풋 테라피 케어 SET — LLM 오염
    "A20251200634",  # 약산성 나이아신아마이드 클렌징 워터 — 판매처 정보 value
    "A20251200638",  # 더 나이아신아마이드 15 세럼 — 판매처 정보 value
    "A20251200641",  # 원스텝 그린 카밍 패드 — 판매처 정보 value
    "A20251200643",  # 약산성 굿모닝 젤 클렌저 — 판매처 정보 value
    "A20251200650",  # 퓨어 핏 시카 크리미 폼 클렌저 — 판매처 정보 value
    "A20251200652",  # 에이씨 컬렉션 카밍 폼 클렌저 — 판매처 정보 value
}

TARGET_PRODUCT_IDS = FALLBACK_PRODUCT_IDS | {
    "A20251200045",  # 워터뱅크 블루 히알루로닉 기초 세트 — value==[]
    "A20251200509",  # 에이피 에이오 리부트 앤 리뉴 에센스 — value==[]
    "A20251200516",  # 에이피 에이오 리부트 앤 리뉴 크림 — value==[]
    "A20251200520",  # 듀얼 리페어 리프트 크림 마스크 — value==[]
    "A20251200523",  # 바이오 컨디셔닝 에센스 하이드로 인핸싱 마스크 — value==[]
    "A20251200763",  # 에이지 어웨이 에스테틱 2종 세트 — value==[]
    "A20251200783",  # 컨센트레이트 시그니처 크림 라이트 — value==[]
    "A20251200810",  # 타임 레스폰스 스킨 리저브 토너 — value==[]
}


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
    return build_skin_care_category_product_prompt(extra_category, document, _SKINCARE_CATEGORIES)


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
