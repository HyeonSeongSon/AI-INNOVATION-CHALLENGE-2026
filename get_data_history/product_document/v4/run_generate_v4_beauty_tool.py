"""
[v4] 뷰티툴 멀티벡터 문서 생성 스크립트

입력:  data/v3_product_data_rewritten_beauty_tool.jsonl
        → structured 필드에서 _original_semantic 제외한 값을 프롬프트 인풋으로 사용
출력:  get_data_history/product_document/v4/v4_product_data_beauty_tool.jsonl

프롬프트 라우팅:
  [그룹 F — 소모품 도구형]
    - 태그: 메이크업툴
    - 태그: 브러쉬
    - 태그: 소품/도구
    - 태그: 수동마사지도구
    - 태그: 뷰티툴케어

  [그룹 D — 기기형]
    - 태그: 헤어기기
    - 태그: 마사지/전동케어
    - 태그: 피부관리
    - 태그: 기타디바이스

각 상품당 생성 필드:
  그룹 F: combined 4개, function_desc 3개, attribute_desc 4개, target_user 2개, spec_feature 1개
  그룹 D: combined 5개, function_desc 5개, attribute_desc 5개, target_user 3개, spec_feature 4개

사용법:
  python run_generate_v4_beauty_tool.py

주의:
  - 이미 처리된 product_id는 건너뜁니다 (재시작 안전).
  - LLM 응답 검증 실패 시 1회 재시도 후 건너뜁니다.
  - 실패한 product_id는 failed_v4_beauty_tool.jsonl에 기록됩니다.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from get_data_history.product_document.v4.prompts_group_d import build_group_d_prompt
from get_data_history.product_document.v4.prompts_group_f import build_group_f_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent.parent.parent.parent / "data"
OUTPUT_DIR  = Path(__file__).parent
INPUT_FILE  = DATA_DIR / "v3_product_data_rewritten_beauty_tool.jsonl"
OUTPUT_FILE = OUTPUT_DIR / "v4_product_data_beauty_tool.jsonl"
FAILED_FILE = OUTPUT_DIR / "failed_v4_beauty_tool.jsonl"
CONCURRENCY = 10

_GROUP_F_TAGS = {"메이크업툴", "브러쉬", "소품/도구", "수동마사지도구", "뷰티툴케어"}
_GROUP_D_TAGS = {"헤어기기", "마사지/전동케어", "피부관리", "기타디바이스"}

_REQUIRED_FIELDS = {
    "F": {
        "combined":      (4, 4),
        "function_desc": (3, 3),
        "attribute_desc":(4, 4),
        "target_user":   (2, 2),
        "spec_feature":  (1, 1),
    },
    "D": {
        "combined":      (5, 5),
        "function_desc": (5, 5),
        "attribute_desc":(5, 5),
        "target_user":   (3, 3),
        "spec_feature":  (4, 4),
    },
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.3)


# ──────────────────────────────────────────────
# 라우팅
# ──────────────────────────────────────────────
def resolve_group(product: dict) -> str:
    tag = product.get("태그", "")
    if tag in _GROUP_F_TAGS:
        return "F"
    if tag in _GROUP_D_TAGS:
        return "D"
    # 미매핑 태그는 경고 후 D로 fallback
    print(f"[WARN] 미매핑 태그 '{tag}' → 그룹D로 처리")
    return "D"


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────
def validate_response(result: dict, group: str) -> list[str]:
    errors: list[str] = []
    for field, (min_count, max_count) in _REQUIRED_FIELDS[group].items():
        val = result.get(field)
        if not isinstance(val, list):
            errors.append(f"{field}: 리스트가 아님 (타입: {type(val).__name__})")
        elif len(val) < min_count:
            errors.append(f"{field}: {len(val)}개 (최소 {min_count}개 필요)")
        elif len(val) > max_count:
            errors.append(f"{field}: {len(val)}개 (최대 {max_count}개 초과)")
        else:
            for i, item in enumerate(val):
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{field}[{i}]: 빈 문자열 또는 비문자열")
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


def build_input_document(product: dict) -> str:
    structured = product.get("structured", {})
    filtered = {k: v for k, v in structured.items() if k != "_original_semantic"}
    return json.dumps(filtered, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 핵심 처리
# ──────────────────────────────────────────────
async def _call_llm_and_validate(prompt: str, group: str) -> tuple[dict | None, list[str]]:
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = parse_llm_json(response.content)
        errors = validate_response(result, group)
        return result, errors
    except Exception as e:
        return None, [f"호출/파싱 오류: {e}"]


async def generate_product(
    product: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> tuple[dict, bool]:
    async with semaphore:
        product_id = product.get("product_id", "?")
        group      = resolve_group(product)
        input_doc  = build_input_document(product)
        prompt     = build_group_d_prompt(input_doc) if group == "D" else build_group_f_prompt(input_doc)

        print(f"[{idx}/{total}] {product_id} (그룹{group}, 태그:{product.get('태그', '')}) 처리 중...")
        result, errors = await _call_llm_and_validate(prompt, group)

        if errors:
            print(f"[{idx}/{total}] {product_id} 검증 실패 — {errors} → 재시도")
            result, errors = await _call_llm_and_validate(prompt, group)

        if errors:
            print(f"[{idx}/{total}] {product_id} 최종 실패 — {errors}")
            return {"product_id": product_id, "group": group}, False

        output_record = {
            "product_id":    product_id,
            "group":         group,
            "combined":      result["combined"],
            "function_desc": result["function_desc"],
            "attribute_desc":result["attribute_desc"],
            "target_user":   result["target_user"],
            "spec_feature":  result["spec_feature"],
        }
        print(f"[{idx}/{total}] {product_id} 완료")
        return output_record, True


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
async def main() -> None:
    if not INPUT_FILE.exists():
        print(f"[ERROR] 입력 파일 없음: {INPUT_FILE}")
        sys.exit(1)

    products: list[dict] = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    group_counts = {"D": 0, "F": 0}
    for p in products:
        group_counts[resolve_group(p)] += 1
    print(f"라우팅 현황 — 그룹D: {group_counts['D']}개, 그룹F: {group_counts['F']}개")

    processed_ids = load_processed_ids(OUTPUT_FILE)
    todo = [p for p in products if p.get("product_id") not in processed_ids]
    total = len(todo)

    if total == 0:
        print("이미 전체 처리 완료")
        return

    print(f"\n총 {total}/{len(products)}개 처리 시작 (동시 {CONCURRENCY}개)")
    print(f"출력 파일: {OUTPUT_FILE}\n")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        generate_product(p, semaphore, i + 1, total)
        for i, p in enumerate(todo)
    ]
    results = await asyncio.gather(*tasks)

    succeeded = [r for r, ok in results if ok]
    failed    = [r for r, ok in results if not ok]

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for r in succeeded:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if failed:
        with open(FAILED_FILE, "a", encoding="utf-8") as f:
            for r in failed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n실패 {len(failed)}건 → {FAILED_FILE.name}")

    print(f"\n완료: {len(succeeded)}/{total} 성공 → {OUTPUT_FILE.name}")


if __name__ == "__main__":
    asyncio.run(main())
