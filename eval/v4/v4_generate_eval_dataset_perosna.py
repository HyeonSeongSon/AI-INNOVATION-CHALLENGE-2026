"""
역방향 합성 평가 데이터셋 생성 스크립트

사용법:
    python eval/generate_eval_dataset.py [--output PATH] [--model MODEL]

동작:
    1. data/test_products_selected.jsonl에서 product_id 목록 로드
    2. 카테고리별 JSONL 파일에서 해당 product_id 필터링
    3. 각 상품에 대해 LLM으로 역방향 페르소나 생성
    4. (persona_info, ground_truth_product_id) 쌍을 JSONL로 저장
"""
import asyncio
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from v4_prompts import build_reverse_persona_prompt

# .env 로드 (backend/app/.env)
_ROOT = Path(__file__).parent.parent.parent  # eval/v4/ → eval/ → project root
load_dotenv(_ROOT / "backend" / "app" / ".env")

# ── 설정 ─────────────────────────────────────────────────────────────────────
SELECTED_FILE = _ROOT / "data" / "test_products_selected.jsonl"

DATA_FILES = {
    "skincare":        _ROOT / "data" / "v4_product_data_skincare.jsonl",
    "color_tone":      _ROOT / "data" / "v4_product_data_color_tone.jsonl",
    "hair":            _ROOT / "data" / "v4_product_data_hair.jsonl",
    "fragrance_body":  _ROOT / "data" / "v4_product_data_fragrance_body.jsonl",
    "inner_beauty":    _ROOT / "data" / "v4_product_data_inner_beauty.jsonl",
    "beauty_tool":     _ROOT / "data" / "v4_product_data_beauty_tool.jsonl",
    "living_supplies": _ROOT / "data" / "v4_product_data_living_supplies.jsonl",
}

# 한국어 카테고리명 → DATA_FILES 키 매핑
CATEGORY_MAP = {
    "스킨케어":  "skincare",
    "뷰티툴":    "beauty_tool",
    "헤어":      "hair",
    "색조":      "color_tone",
    "향수/바디": "fragrance_body",
    "이너뷰티":  "inner_beauty",
    "생활도구":  "living_supplies",
}

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_OUTPUT = _ROOT / "eval" / "v4_synthetic_eval_dataset.jsonl"
TEST_OUTPUT    = _ROOT / "eval" / "v4_synthetic_eval_dataset_test.jsonl"
MAX_CONCURRENT = 5                  # 동시 API 호출 수 (rate limit 방지)
NUM_PERSONAS   = 1                  # 상품당 기본 페르소나 생성 수
# ──────────────────────────────────────────────────────────────────────────────


def load_products(file_path: Path) -> list[dict]:
    products = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def load_selected_products(max_per_category: int | None = None) -> list[dict]:
    """test_products_selected.jsonl의 product_id를 기반으로 상품 데이터 로드

    Args:
        max_per_category: 카테고리당 최대 상품 수 (None이면 전체)
    """
    # 1. 선택된 product_id를 카테고리(영문 키)별로 분류
    selected: dict[str, list[str]] = {}
    with open(SELECTED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            cat_kr = item.get("카테고리", "")
            cat_en = CATEGORY_MAP.get(cat_kr)
            if not cat_en:
                print(f"[warn] 알 수 없는 카테고리: {cat_kr}")
                continue
            selected.setdefault(cat_en, []).append(item["product_id"])

    # 2. 각 카테고리 파일에서 해당 product_id 필터링
    products = []
    for category, ids in selected.items():
        if max_per_category is not None:
            ids = ids[:max_per_category]
        path = DATA_FILES.get(category)
        if not path or not path.exists():
            print(f"[skip] {category} 파일 없음")
            continue
        id_set = set(ids)
        found = [p for p in load_products(path) if p.get("product_id") in id_set]
        if max_per_category is not None:
            found = found[:max_per_category]
        for p in found:
            p["_source_category"] = category
        products.extend(found)
        print(f"[load] {category}: {len(ids)}개 요청 → {len(found)}개 로드")

    return products


async def generate_persona(
    client: AsyncOpenAI,
    product: dict,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """상품 1개에 대해 역방향 페르소나 생성"""
    product_id = product.get("product_id", "unknown")
    prompt = build_reverse_persona_prompt(product)

    # null byte, 제어 문자, BOM/비문자(U+FEFF, U+FFFE, U+FFFF) 제거 (HTTP JSON body 파싱 오류 방지)
    _BAD = frozenset("\ufeff\ufffe\uffff")
    prompt = "".join(ch for ch in prompt if (ch >= " " or ch in "\n\t") and ch not in _BAD)

    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            persona_json = response.choices[0].message.content
            persona_info = json.loads(persona_json)
            return persona_info

        except Exception as e:
            print(f"[error] {product_id} 페르소나 생성 실패: {e}")
            return None


def build_eval_record(product: dict, persona_info: dict, persona_idx: int = 0) -> dict:
    """평가 레코드 구성"""
    return {
        "eval_id": f"eval_{product.get('product_id', 'unknown')}_{persona_idx:02d}",
        "source_product_id": product.get("product_id"),
        "source_product_category": product.get("_source_category", ""),
        # 역생성된 페르소나 (PersonaClient.get_persona_info() 출력과 동일 구조)
        "persona_info": persona_info,
        # Ground truth: 시드 상품이 주요 정답 (relevance=3)
        "ground_truth": {
            "product_ids": [product.get("product_id")],
            "relevance_grades": {
                product.get("product_id"): 3
            },
        },
        # 참고용: v4 상품 원문 필드
        "_reference": {
            "combined":       product.get("combined", []),
            "function_desc":  product.get("function_desc", []),
            "attribute_desc": product.get("attribute_desc", []),
            "target_user":    product.get("target_user", []),
            "spec_feature":   product.get("spec_feature", []),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def main(model: str, output_path: Path, test_mode: bool = False, num_personas: int = NUM_PERSONAS):
    mode_label = "[TEST] 카테고리별 1개" if test_mode else "전체"
    print(f"\n{'='*60}")
    print(f"역방향 합성 평가 데이터셋 생성 ({mode_label})")
    print(f"  선택 파일: {SELECTED_FILE.name}")
    print(f"  LLM 모델: {model}")
    print(f"  상품당 페르소나: {num_personas}개")
    print(f"  출력 파일: {output_path}")
    print(f"{'='*60}\n")

    # 1. 선택된 상품 로드
    products = load_selected_products(max_per_category=1 if test_mode else None)
    total = len(products) * num_personas
    print(f"\n총 {len(products)}개 상품 × {num_personas}개 페르소나 = {total}개 레코드 생성 시작...\n")

    # 2. 기존 파일에서 이미 생성된 eval_id 로드 (중복 방지)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_ids.add(json.loads(line)["eval_id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        print(f"[resume] 기존 {len(existing_ids)}개 레코드 발견 → 중복 건너뜀\n")

    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    done_count = 0
    success = 0
    skipped = 0

    async def process(product: dict, out_file):
        nonlocal done_count, success, skipped
        product_id = product.get("product_id")
        for idx in range(num_personas):
            eval_id = f"eval_{product_id}_{idx:02d}"
            if eval_id in existing_ids:
                done_count += 1
                skipped += 1
                print(f"[{done_count}/{total}] [skip] {eval_id} - 이미 존재")
                continue
            persona = await generate_persona(client, product, model, semaphore)
            done_count += 1
            if persona is None:
                print(f"[{done_count}/{total}] [skip] {eval_id} - 페르소나 생성 실패")
                continue
            record = build_eval_record(product, persona, persona_idx=idx)
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            success += 1
            print(f"[{done_count}/{total}] [done] {eval_id} ({product.get('_source_category')}) → {persona.get('나이', '?')}세")

    # 3. 기존 파일에 이어쓰기 (append 모드)
    with open(output_path, "a", encoding="utf-8") as f:
        await asyncio.gather(*[process(p, f) for p in products])

    print(f"\n{'='*60}")
    print(f"완료: {success}개 신규 생성, {skipped}개 중복 건너뜀 (총 {total}개 처리) → {output_path}")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="역방향 합성 평가 데이터셋 생성")
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help=f"출력 파일 경로 (기본값: {DEFAULT_OUTPUT}, --test 시: {TEST_OUTPUT.name})"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="테스트 모드: 카테고리별 1개씩만 생성 (출력: synthetic_eval_dataset_test.jsonl)"
    )
    parser.add_argument(
        "--num-personas", type=int, default=NUM_PERSONAS,
        help=f"상품당 생성할 페르소나 수 (기본값: {NUM_PERSONAS})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.output:
        out = Path(args.output)
    else:
        out = TEST_OUTPUT if args.test else DEFAULT_OUTPUT
    asyncio.run(main(
        model=args.model,
        output_path=out,
        test_mode=args.test,
        num_personas=args.num_personas,
    ))