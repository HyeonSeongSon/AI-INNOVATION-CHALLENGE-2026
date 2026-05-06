"""
[v4] 프래그런스/바디 멀티벡터 문서 생성 스크립트

입력:  data/v3_product_data_rewritten_fragrance_body.jsonl
        → structured 필드에서 _original_semantic 제외한 값을 프롬프트 인풋으로 사용
출력:  get_data_history/product_document/v4/v4_product_data_fragrance_body.jsonl

프롬프트 라우팅:
  [그룹 C — 감각/무드형]
    - 태그: 향수
    - 태그: 홈프래그런스
    - 태그: 바디케어 + 서브태그: 입욕제/배쓰밤

  [그룹 A — 피부/고민형]
    - 태그: 바디세정
    - 태그: 바디케어 (입욕제/배쓰밤 제외 나머지)
    - 태그: 여성청결제

각 상품당 생성 필드:
  그룹 C: combined 7개, function_desc 3개, attribute_desc 4개, target_user 3개, spec_feature 1개
  그룹 A: combined 6개, function_desc 5개, attribute_desc 3개, target_user 6개, spec_feature 2개

사용법:
  python run_generate_v4_fragrance_body.py

주의:
  - 이미 처리된 product_id는 건너뜁니다 (재시작 안전).
  - LLM 응답 검증 실패 시 1회 재시도 후 건너뜁니다.
  - 실패한 product_id는 failed_v4_fragrance_body.jsonl에 기록됩니다.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from get_data_history.product_document.v4.prompts_group_a import build_group_a_prompt
from get_data_history.product_document.v4.prompts_group_c import build_group_c_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent.parent.parent.parent / "data"
OUTPUT_DIR  = Path(__file__).parent
INPUT_FILE  = DATA_DIR / "v3_product_data_rewritten_fragrance_body.jsonl"
OUTPUT_FILE = OUTPUT_DIR / "v4_product_data_fragrance_body.jsonl"
FAILED_FILE = OUTPUT_DIR / "failed_v4_fragrance_body.jsonl"
CONCURRENCY = 10

# 필드별 필요 개수: {그룹: {필드: (min, max)}}
_REQUIRED_FIELDS = {
    "C": {
        "combined":      (7, 7),
        "function_desc": (3, 3),
        "attribute_desc":(4, 4),
        "target_user":   (3, 3),
        "spec_feature":  (1, 1),
    },
    "A": {
        "combined":      (6, 6),
        "function_desc": (5, 5),
        "attribute_desc":(3, 3),
        "target_user":   (6, 6),
        "spec_feature":  (2, 2),
    },
}

llm = get_llm(Settings.chatgpt_model_name, temperature=0.3)


# ──────────────────────────────────────────────
# 라우팅
# ──────────────────────────────────────────────
def resolve_group(product: dict) -> str:
    """태그/서브태그 기반으로 사용할 프롬프트 그룹 결정."""
    tag    = product.get("태그", "")
    subtag = product.get("서브태그", "")

    if tag in ("향수", "홈프래그런스"):
        return "C"
    if tag == "바디케어" and subtag == "입욕제/배쓰밤":
        return "C"
    # 바디세정, 바디케어(입욕제/배쓰밤 제외), 여성청결제
    return "A"


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
        prompt     = build_group_c_prompt(input_doc) if group == "C" else build_group_a_prompt(input_doc)

        print(f"[{idx}/{total}] {product_id} (그룹{group}, 태그:{product.get('태그','')} / 서브태그:{product.get('서브태그','')}) 처리 중...")
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

    # 라우팅 현황 출력
    group_counts = {"A": 0, "C": 0}
    for p in products:
        group_counts[resolve_group(p)] += 1
    print(f"라우팅 현황 — 그룹A: {group_counts['A']}개, 그룹C: {group_counts['C']}개")

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
