"""
product_data_structured_inner_beauty_t1.jsonl 에서
추출 실패 및 품질 문제 항목을 재처리.

감지 기준:
  - structured == {}
  - 문서가 빈 경우 (문서 길이 1200자 미만 → 모든 섹션이 없음으로 채워진 경우)
  - RETRY_IDS에 포함된 product_id (품질 문제 확인된 항목)

재처리 방식:
  - 문서가 정상인 경우: 기존 문서 사용
  - 문서가 빈 경우 또는 structured == {}: 상품명 + 한줄소개 + 태그 기반 텍스트 사용
"""

import json
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from document_inner_beauty_prompt import build_inner_beauty_category_product_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "product_data_structured_inner_beauty_t1.jsonl"
CONCURRENCY = 5

_CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
with open(_CATEGORIES_FILE, encoding="utf-8") as _f:
    _INNER_BEAUTY_CATEGORIES: list[str] = json.load(_f)["category_type"]["이너뷰티"]

TAG_TO_EXTRA_CATEGORY: dict[str, str] = {
    "슬리밍":       "inner_beauty",
    "이너뷰티":     "inner_beauty",
    "영양보충":     "inner_beauty",
    "브렌딩티/차":  "tea",
    "차세트":       "tea",
}

# 품질 문제 확인된 product_id 재처리 목록
RETRY_IDS = {
    "A20251200264",  # 슈퍼콜라겐 프리미엄 - 거의 blank
    "A20251200832",  # 세작 피라미드 - 빈 문서
    "A20251200245",  # 메타그린 칼로리컷 젤리 - daily_intake, key_nutrients 누락
    "A20251200246",  # 메타그린 부스터샷 7일 - daily_intake, key_nutrients 누락
    "A20251200252",  # 멀티비타민미네랄 150정 - function_claim 누락
    "A20251200263",  # 명작수 골드 - key_nutrients, function_claim 누락
    "A20251200793",  # 미라클 타임 20포 - key_nutrients, function_claim 누락
    "A20251200261",  # 메타그린 클린티 - caffeine 누락
    "A20251200818",  # 프리미엄 티 컬렉션 10종 - caffeine 누락
    "A20251200822",  # 삼다 꿀배 티 - caffeine 누락
    "A20251200824",  # 달빛걷기 20입 - caffeine 누락
    "A20251200831",  # 제주 삼다 영귤 티 - caffeine 누락
    "A20251200833",  # 제주 말차 밀크티 - caffeine 누락
    "A20251200836",  # 러블리 티박스 4종 - caffeine 누락
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)


def is_empty_document(product: dict) -> bool:
    """문서 내용이 사실상 없는 경우 (길이 1200자 미만)"""
    return len(product.get("문서", "")) < 1200


def build_fallback_document(product: dict) -> str:
    """문서 대신 상품명 + 한줄소개 + 태그로 대체 문서 생성"""
    brand = product.get("브랜드", "")
    name = product.get("상품명", "")
    tag = product.get("태그", "")
    intro = product.get("한줄소개", "")
    return (
        f"브랜드: {brand}\n"
        f"상품명: {name}\n"
        f"카테고리: {tag}\n"
        f"상품 소개: {intro}"
    )


def build_prompt(product: dict) -> str:
    tag = product.get("태그", "")
    extra_category = TAG_TO_EXTRA_CATEGORY.get(tag)
    if is_empty_document(product) or product.get("structured") == {}:
        document = build_fallback_document(product)
    else:
        document = product.get("문서", "")
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


async def process_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    async with semaphore:
        product_id = product.get("product_id", "?")
        use_fallback = is_empty_document(product) or product.get("structured") == {}
        mode = "상품명 기반" if use_fallback else "문서 기반"
        print(f"[{idx}/{total}] {product_id} 재처리 중 ({mode})...")
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

    targets = [
        (i, r) for i, r in enumerate(all_records)
        if r.get("structured") == {} or r.get("product_id") in RETRY_IDS
    ]
    total = len(targets)

    if total == 0:
        print("재처리할 항목이 없습니다.")
        return

    print(f"재처리 대상 {total}개:")
    for _, r in targets:
        use_fallback = is_empty_document(r) or r.get("structured") == {}
        mode = "상품명 기반" if use_fallback else "문서 기반"
        print(f"  - [{r.get('product_id')}] {r.get('상품명')} ({mode})")

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
