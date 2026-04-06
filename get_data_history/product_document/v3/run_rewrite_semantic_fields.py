"""
의미 기반 검색 필드 4개(function_desc / attribute_desc / combined / target_user)를
소비자 언어로 재작성하는 스크립트

입력:  data/v2_product_data_structured_*.jsonl
출력:  data/v3_product_data_rewritten_*.jsonl  (structured 필드 내 4개 필드만 교체)

사용법:
  python run_rewrite_semantic_fields.py [카테고리]
  예) python run_rewrite_semantic_fields.py skincare
  예) python run_rewrite_semantic_fields.py          # 전체 카테고리

주의:
  - 이미 처리된 product_id는 건너뜁니다 (재시작 안전).
  - LLM 응답 검증 실패 시 1회 재시도 후 원본을 유지합니다.
  - 실패한 product_id는 failed_*.jsonl에 기록됩니다.
"""

import asyncio
import json
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
# 검증 대상 필드 및 최소/최대 조건 (min, max)
_REQUIRED_STR_FIELDS = ("function_desc", "attribute_desc", "target_user", "combined")
_REQUIRED_LIST_FIELDS: dict[str, tuple[int, int]] = {
    "function_tags":  (3, 10),
    "attribute_tags": (3, 10),
    "target_tags":    (3, 10),
    "search_tags":    (5, 20),
    "search_phrases": (5, 10),
}

# 이미지 판독 불가 등 오류 시그널 — 이 문자열이 str 필드에 포함되면 실패 처리
_ERROR_SIGNAL_SUBSTRINGS = (
    "판독 불가",
    "이미지 저해상도",
    "원본 이미지 필요",
    "정보 부족",
    "이미지 판독",
    "텍스트 제공 요청",
)


def validate_rewritten(rewritten: dict) -> list[str]:
    """LLM 출력 검증. 오류 메시지 리스트 반환 (빈 리스트 = 통과)."""
    errors: list[str] = []

    # LLM이 선택지 요청 등 비정상 응답을 반환한 경우
    if "request" in rewritten or "options" in rewritten:
        errors.append("LLM이 JSON 필드 대신 선택지/질문을 반환함")
        return errors  # 나머지 검사 불필요

    # 이미지 판독 불가 등 오류 시그널 감지
    for field in _REQUIRED_STR_FIELDS:
        val = rewritten.get(field, "")
        if isinstance(val, str) and any(sig in val for sig in _ERROR_SIGNAL_SUBSTRINGS):
            errors.append(f"{field}: 오류 시그널 감지 — '{val[:40]}...'")
            return errors  # 나머지 검사 불필요

    for field in _REQUIRED_STR_FIELDS:
        val = rewritten.get(field, "")
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{field}: 비어있음")

    for field, (min_count, max_count) in _REQUIRED_LIST_FIELDS.items():
        val = rewritten.get(field, [])
        if not isinstance(val, list):
            errors.append(f"{field}: 리스트가 아님")
        elif len(val) < min_count:
            errors.append(f"{field}: {len(val)}개 (최소 {min_count}개 필요)")
        elif len(val) > max_count:
            errors.append(f"{field}: {len(val)}개 (최대 {max_count}개 초과)")

    return errors


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
async def _call_llm_and_validate(prompt: str) -> tuple[dict | None, list[str]]:
    """LLM 호출 → 파싱 → 검증. (결과, 오류목록) 반환."""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        rewritten = parse_llm_json(response.content)
        errors = validate_rewritten(rewritten)
        return rewritten, errors
    except Exception as e:
        return None, [f"호출/파싱 오류: {e}"]


async def rewrite_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> tuple[dict, bool]:
    """structured 내 4개 필드를 소비자 언어로 재작성.
    반환: (결과 product dict, 성공 여부)
    """
    async with semaphore:
        product_id = product.get("product_id", "?")
        structured = product.get("structured", {})

        # 재작성 대상 필드 추출 (원본 보존용)
        fields_to_rewrite = {
            k: structured.get(k, "")
            for k in ("function_desc", "attribute_desc", "combined", "target_user")
        }
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

        rewritten, errors = await _call_llm_and_validate(prompt)

        # 검증 실패 시 1회 재시도
        if errors:
            print(f"[{idx}/{total}] {product_id} 검증 실패 — {errors} → 재시도")
            rewritten, errors = await _call_llm_and_validate(prompt)

        if errors:
            print(f"[{idx}/{total}] {product_id} 최종 실패 — {errors}")
            return product, False  # 원본 유지

        # 4개 필드 교체 + tags 5개 추가, 나머지는 유지
        new_structured = {**structured, **rewritten}
        new_structured["_original_semantic"] = fields_to_rewrite

        print(f"[{idx}/{total}] {product_id} 완료")
        return {**product, "structured": new_structured}, True


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

    # 이미 처리된 항목 제외
    processed_ids = load_processed_ids(output_file)
    todo = [p for p in products if p.get("product_id") not in processed_ids]
    total = len(todo)

    if total == 0:
        print(f"[{category}] 이미 전체 처리 완료")
        return

    print(f"\n[{category}] {total}/{len(products)}개 처리 시작 (동시 {CONCURRENCY}개)")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        rewrite_product(p, semaphore, i + 1, total)
        for i, p in enumerate(todo)
    ]
    results = await asyncio.gather(*tasks)

    # 성공/실패 분리
    succeeded = [(r, ok) for r, ok in results if ok]
    failed    = [(r, ok) for r, ok in results if not ok]

    # 성공 결과 저장 (추가 모드, 재시작 안전)
    with open(output_file, "a", encoding="utf-8") as f:
        for r, _ in succeeded:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 실패 product_id 별도 기록
    if failed:
        failed_file = DATA_DIR / f"failed_{category}.jsonl"
        with open(failed_file, "a", encoding="utf-8") as f:
            for r, _ in failed:
                f.write(json.dumps({"product_id": r.get("product_id"), "category": category}, ensure_ascii=False) + "\n")
        print(f"[{category}] 실패 {len(failed)}건 → {failed_file.name}")

    print(f"[{category}] 완료: {len(succeeded)}/{total} 성공 → {output_file.name}")


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
