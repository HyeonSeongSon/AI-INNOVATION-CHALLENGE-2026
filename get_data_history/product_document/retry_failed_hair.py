"""
product_data_structured_hair.jsonl 에서 structured == {} 인 항목만 재처리.
성공하면 기존 레코드를 교체하고, 여전히 실패한 항목은 {} 그대로 남김.
"""

import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from document_hair_prompt import build_hair_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_hair.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _HAIR_CATEGORIES: list[str] = json.load(_f)["category_type"]["헤어"]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "샴푸":             "hair_cleansing",
    "린스&컨디셔너":    "hair_cleansing",
    "트리트먼트&팩":    "hair_treatment",
    "에센스&세럼&오일": "hair_treatment",
    "스타일링":         "hair_styling_",
    "헤어컬러":         "hair_color",
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    document = product.get("문서", "")
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


async def process_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    async with semaphore:
        product_id = product.get("product_id", "?")
        print(f"[{idx}/{total}] {product_id} 재처리 중...")
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
    # 기존 파일 읽기
    all_records: list[dict] = []
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_records.append(json.loads(line))

    # 실패 항목(structured == {}) 분리
    failed = [(i, r) for i, r in enumerate(all_records) if r.get("structured") == {}]
    total = len(failed)

    if total == 0:
        print("재처리할 실패 항목이 없습니다.")
        return

    print(f"실패 항목 {total}개 재처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_product(record, semaphore, idx + 1, total)
        for idx, (_, record) in enumerate(failed)
    ]
    retried = await asyncio.gather(*tasks)

    # 원본 리스트에서 실패 항목 교체
    for (orig_idx, _), new_record in zip(failed, retried):
        all_records[orig_idx] = new_record

    # structured == {} 인 항목 제거
    before = len(all_records)
    all_records = [r for r in all_records if r.get("structured") != {}]
    removed = before - len(all_records)

    # 파일 덮어쓰기
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for _, r in enumerate(retried) if r.get("structured"))
    print(f"\n재처리 결과: {success}/{total} 성공")
    if removed:
        print(f"여전히 실패한 항목 {removed}개 제거됨")
    print(f"최종 저장: {len(all_records)}개 → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
