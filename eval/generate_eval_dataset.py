"""
역방향 합성 평가 데이터셋 생성 스크립트

사용법:
    python eval/generate_eval_dataset.py [--samples N] [--output PATH] [--model MODEL]

동작:
    1. data/ 디렉토리의 상품 JSONL 파일들을 카테고리별 로드
    2. 카테고리별 균등 샘플링
    3. 각 상품에 대해 LLM으로 역방향 페르소나 생성
    4. (persona_info, ground_truth_product_id) 쌍을 JSONL로 저장
"""
import asyncio
import json
import random
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from prompts import build_reverse_persona_prompt

# .env 로드 (backend/app/.env)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / "backend" / "app" / ".env")

# ── 설정 ─────────────────────────────────────────────────────────────────────
DATA_FILES = {
    "skincare":       _ROOT / "data" / "product_data_structured_skincare.jsonl",
    "color_tone":     _ROOT / "data" / "product_data_structured_color_tone.jsonl",
    "hair":           _ROOT / "data" / "product_data_structured_hair.jsonl",
    "fragrance_body": _ROOT / "data" / "product_data_structured_fragrance_body.jsonl",
    "inner_beauty":   _ROOT / "data" / "product_data_structured_inner_beauty.jsonl",
    "beauty_tool":    _ROOT / "data" / "product_data_structured_beauty_tool.jsonl",
    "nail":           _ROOT / "data" / "product_data_structured_nail.jsonl",
}

DEFAULT_SAMPLES_PER_CATEGORY = 7   # 카테고리 7개 × 7 = 49개
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_OUTPUT = _ROOT / "eval" / "synthetic_eval_dataset.jsonl"
MAX_CONCURRENT = 5                  # 동시 API 호출 수 (rate limit 방지)
RANDOM_SEED = 42
# ──────────────────────────────────────────────────────────────────────────────


def load_products(file_path: Path) -> list[dict]:
    products = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def sample_products(samples_per_category: int, seed: int = RANDOM_SEED) -> list[dict]:
    """카테고리별 균등 샘플링 (상품 수가 적은 카테고리는 전체 사용)"""
    rng = random.Random(seed)
    sampled = []

    for category, path in DATA_FILES.items():
        if not path.exists():
            print(f"[skip] {path.name} 파일 없음")
            continue
        products = load_products(path)
        n = min(samples_per_category, len(products))
        chosen = rng.sample(products, n)
        for p in chosen:
            p["_source_category"] = category  # 내부 추적용
        sampled.extend(chosen)
        print(f"[load] {category}: {len(products)}개 중 {n}개 샘플링")

    return sampled


async def generate_persona(
    client: AsyncOpenAI,
    product: dict,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """상품 1개에 대해 역방향 페르소나 생성"""
    product_id = product.get("product_id", "unknown")
    prompt = build_reverse_persona_prompt(product)

    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.8,  # 다양한 페르소나 생성
            )
            persona_json = response.choices[0].message.content
            persona_info = json.loads(persona_json)
            return persona_info

        except Exception as e:
            print(f"[error] {product_id} 페르소나 생성 실패: {e}")
            return None


def build_eval_record(product: dict, persona_info: dict) -> dict:
    """평가 레코드 구성"""
    s = product.get("structured", {})
    return {
        "eval_id": f"eval_{product.get('product_id', 'unknown')}",
        "source_product_id": product.get("product_id"),
        "source_product_name": product.get("상품명", ""),
        "source_product_category": product.get("_source_category", ""),
        "source_product_tag": product.get("태그", ""),
        "source_product_brand": product.get("브랜드", ""),
        # 역생성된 페르소나 (PersonaClient.get_persona_info() 출력과 동일 구조)
        "persona_info": persona_info,
        # Ground truth: 시드 상품이 주요 정답 (relevance=3)
        "ground_truth": {
            "product_ids": [product.get("product_id")],
            "relevance_grades": {
                product.get("product_id"): 3
            },
        },
        # 참고용: 상품의 target_user 원문
        "_reference": {
            "target_user": s.get("target_user", ""),
            "concern": s.get("concern", []),
            "suitable_for": s.get("suitable_for", []),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def main(
    samples_per_category: int,
    model: str,
    output_path: Path,
    seed: int = RANDOM_SEED,
):
    print(f"\n{'='*60}")
    print(f"역방향 합성 평가 데이터셋 생성")
    print(f"  카테고리당 샘플 수: {samples_per_category}")
    print(f"  LLM 모델: {model}")
    print(f"  출력 파일: {output_path}")
    print(f"{'='*60}\n")

    # 1. 상품 샘플링
    products = sample_products(samples_per_category, seed=seed)
    print(f"\n총 {len(products)}개 상품에 대해 페르소나 생성 시작...\n")

    # 2. 비동기 페르소나 생성
    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    tasks = [
        generate_persona(client, product, model, semaphore)
        for product in products
    ]
    personas = await asyncio.gather(*tasks)

    # 3. 결과 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    success = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for product, persona in zip(products, personas):
            if persona is None:
                print(f"[skip] {product.get('product_id')} - 페르소나 생성 실패")
                continue
            record = build_eval_record(product, persona)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            success += 1
            print(f"[done] {product.get('product_id')} ({product.get('_source_category')}) → {persona.get('이름', '?')}, {persona.get('나이', '?')}세")

    print(f"\n{'='*60}")
    print(f"완료: {success}/{len(products)}개 생성 → {output_path}")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="역방향 합성 평가 데이터셋 생성")
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES_PER_CATEGORY,
        help=f"카테고리당 샘플 수 (기본값: {DEFAULT_SAMPLES_PER_CATEGORY})"
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"출력 파일 경로 (기본값: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--seed", type=int, default=RANDOM_SEED,
        help=f"랜덤 시드 (기본값: {RANDOM_SEED})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        samples_per_category=args.samples,
        model=args.model,
        output_path=Path(args.output),
        seed=args.seed,
    ))
