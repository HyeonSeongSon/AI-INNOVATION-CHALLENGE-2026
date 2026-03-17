"""
product_data_structured_fragrance_body.jsonl 에서
문서(이미지 판독 실패)로 인해 structured가 오염된 항목을 재처리.

감지 기준:
  - 문서가 이미지 판독 실패 응답("옵션 A", "옵션 B" 등 포함)인 경우
  - 또는 structured == {}

재처리 방식:
  - 문서 대신 상품명 + 한줄소개 + 태그 기반 텍스트를 입력으로 사용
"""

import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from document_fragrance_and_body_prompt import build_fragrance_body_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_fragrance_body.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _FRAGRANCE_BODY_CATEGORIES: list[str] = json.load(_f)["category_type"]["향수/바디"]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "향수":                 "fragrance",
    "샤워코롱":             "fragrance",
    "향수세트":             "fragrance",
    "바디워시":             "body_cleansing",
    "바디스크럽":           "body_cleansing",
    "비누":                 "body_cleansing",
    "여성청결제":           "feminine_care",
    "바디모이스처라이저":   "body_care",
    "바디오일&미스트":      "body_care",
    "핸드&풋케어":          "body_care",
    "데오드란트":           "body_care",
    "입욕제/배쓰밤":        "body_care",
    "캔들&디퓨져":          "home_fragrance",
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)


def is_bad_document(product: dict) -> bool:
    """이미지 판독 실패로 문서가 오염된 경우 감지"""
    doc = product.get("문서", "")
    bad_signals = ["옵션 A", "옵션 B", "이미지 분석을 바로 진행", "고해상도", "세로로 축소"]
    return any(signal in doc for signal in bad_signals)


def build_fallback_document(product: dict) -> str:
    """문서 대신 상품명 + 한줄소개 + 태그로 대체 문서 생성"""
    name = product.get("상품명", "")
    intro = product.get("한줄소개", "")
    tag = product.get("태그", "")
    brand = product.get("브랜드", "")
    return (
        f"브랜드: {brand}\n"
        f"상품명: {name}\n"
        f"카테고리: {tag}\n"
        f"상품 소개: {intro}"
    )


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag)
    document = build_fallback_document(product)
    return build_fragrance_body_category_product_prompt(extra_category, document, _FRAGRANCE_BODY_CATEGORIES)


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
        print(f"[{idx}/{total}] {product_id} 재처리 중 (상품명 기반)...")
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
    all_records: list[dict] = []
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_records.append(json.loads(line))

    # 재처리 대상: structured == {} 또는 문서 오염 항목
    targets = [
        (i, r) for i, r in enumerate(all_records)
        if r.get("structured") == {} or is_bad_document(r)
    ]
    total = len(targets)

    if total == 0:
        print("재처리할 항목이 없습니다.")
        return

    print(f"재처리 대상 {total}개:")
    for _, r in targets:
        print(f"  - [{r.get('product_id')}] {r.get('상품명')}")

    print(f"\n재처리 시작 (동시 {CONCURRENCY}개)")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(record, semaphore, idx + 1, total)
        for idx, (_, record) in enumerate(targets)
    ]
    retried = await asyncio.gather(*tasks)

    for (orig_idx, _), new_record in zip(targets, retried):
        all_records[orig_idx] = new_record

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in retried if r.get("structured"))
    print(f"\n재처리 결과: {success}/{total} 성공 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
