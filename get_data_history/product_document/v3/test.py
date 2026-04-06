"""
의미 기반 검색 필드 4개(function_desc / attribute_desc / combined / target_user)를
소비자 언어로 재작성하는 스크립트

입력:  data/v2_product_data_structured_*.jsonl
출력:  data/v3_product_data_rewritten_*.jsonl  (structured 필드 내 4개 필드만 교체)

사용법:
  python run_rewrite_semantic_fields.py [카테고리]
  예) python run_rewrite_semantic_fields.py skincare
  예) python run_rewrite_semantic_fields.py          # 전체 카테고리

주의: 이미 처리된 product_id는 건너뜁니다 (재시작 안전).
"""

import asyncio
import json
import random
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from get_data_history.product_document.v3.rewrite_semantic_fields_prompt import (
    build_rewrite_semantic_fields_prompt,
)
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent.parent.parent.parent / "data"
CONCURRENCY = 10  # 동시 LLM 호출 수

CATEGORIES = [
    "skincare",
    "color_tone",
    "hair",
    "fragrance_body",
    "inner_beauty",
    "beauty_tool",
    "living_supplies",
]

llm = get_llm(Settings.chatgpt_model_name, temperature=0.3)


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────
def parse_llm_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


def load_processed_ids(output_file: Path) -> set[str]:
    """이미 처리된 product_id 목록 로드 (재시작 안전)"""
    if not output_file.exists():
        return set()
    processed = set()
    with open(output_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    processed.add(json.loads(line)["product_id"])
                except Exception:
                    pass
    return processed


# ──────────────────────────────────────────────
# 핵심 처리
# ──────────────────────────────────────────────
async def rewrite_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    """structured 내 4개 필드를 소비자 언어로 재작성"""
    async with semaphore:
        product_id = product.get("product_id", "?")
        structured = product.get("structured", {})

        # 재작성 대상 필드 추출 (원본 보존용)
        fields_to_rewrite = {
            k: structured.get(k, "")
            for k in ("function_desc", "attribute_desc", "combined", "target_user")
        }
        # 새로 생성되는 tags 필드 (원본에 없는 필드)
        NEW_FIELDS = (
            "function_tags", "attribute_tags", "target_tags",
            "search_tags", "search_phrases",
        )
        # 컨텍스트로 핵심 필드 추가
        context_fields = {
            k: structured.get(k, "")
            for k in ("category", "summary", "concern", "ingredient",
                      "texture", "value", "function", "attribute",
                      "key_benefits", "suitable_for")
        }
        input_doc = json.dumps(
            {**context_fields, **fields_to_rewrite},
            ensure_ascii=False,
            indent=2,
        )

        print(f"[{idx}/{total}] {product_id} 처리 중...")
        prompt = build_rewrite_semantic_fields_prompt(input_doc)

        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            rewritten = parse_llm_json(response.content)

            # 4개 필드 교체 + search_tags / search_phrases 추가, 나머지는 유지
            new_structured = {**structured, **rewritten}
            # 원본 보존 (비교/롤백용)
            new_structured["_original_semantic"] = fields_to_rewrite

            print(f"[{idx}/{total}] {product_id} 완료")
            return {**product, "structured": new_structured}

        except Exception as e:
            print(f"[{idx}/{total}] {product_id} 실패 — {e}")
            return product  # 실패 시 원본 유지


# ──────────────────────────────────────────────
# 카테고리별 실행
# ──────────────────────────────────────────────
async def process_category(category: str) -> None:
    input_file  = DATA_DIR / f"v2_product_data_structured_{category}.jsonl"
    output_file = DATA_DIR / f"v3_product_data_rewritten_{category}.jsonl"

    if not input_file.exists():
        print(f"[SKIP] {input_file.name} 없음")
        return

    # 전체 로드
    products: list[dict] = []
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    # 카테고리별 5개 랜덤 샘플
    sample = random.sample(products, min(5, len(products)))

    # 이미 처리된 항목 제외
    processed_ids = load_processed_ids(output_file)
    todo = [p for p in sample if p.get("product_id") not in processed_ids]
    total = len(todo)

    if total == 0:
        print(f"[{category}] 이미 전체 처리 완료")
        return

    print(f"\n[{category}] {total}/{len(sample)}개 처리 시작 (샘플 {len(sample)}/{len(products)}, 동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        rewrite_product(p, semaphore, i + 1, total)
        for i, p in enumerate(todo)
    ]
    results = await asyncio.gather(*tasks)

    # 추가 모드로 저장 (재시작 안전)
    with open(output_file, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in results if r.get("structured", {}).get("_original_semantic"))
    print(f"[{category}] 완료: {success}/{total} 성공 → {output_file.name}")


async def main(target_categories: list[str]) -> None:
    for cat in target_categories:
        await process_category(cat)
    print("\n전체 완료")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cats = [sys.argv[1]]
    else:
        cats = CATEGORIES

    asyncio.run(main(cats))