import asyncio
import json
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).parent))  # eval/ 디렉토리 (prompts.py)

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from openai import AsyncOpenAI
from v3_prompts import build_reverse_persona_prompt

_EVAL_DIR      = Path(__file__).parent
_DATA_DIR      = _ROOT / "data"
DEFAULT_OUTPUT = _EVAL_DIR / "synthetic_eval_dataset.jsonl"
DEFAULT_MODEL  = "gpt-5-mini"
DEFAULT_CONCURRENCY = 5
NUM_PERSONAS   = 3

# 재생성 대상 product_id 목록
TARGET_PRODUCT_IDS = {
    # "A20251200045",
    # "A20251200530",
    "A20251200151",
    # "A20251200160",
    # "A20251200052"
}


def load_hair_products() -> list[dict]:
    """living_supplies 데이터 파일에서 대상 상품만 로드"""
    path = _DATA_DIR / "v2_product_data_structured_skincare.jsonl"
    products = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                p = json.loads(line)
                if p.get("product_id") in TARGET_PRODUCT_IDS:
                    p["_source_category"] = "skincare"
                    products.append(p)
    return products


def load_eval_cache(path: Path) -> dict[str, dict]:
    """기존 eval 데이터셋을 {eval_id: record} 딕셔너리로 로드"""
    cache: dict[str, dict] = {}
    if not path.exists():
        return cache
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    cache[record["eval_id"]] = record
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def build_eval_record(product: dict, persona_info: dict, persona_idx: int) -> dict:
    """generate_eval_dataset.py의 build_eval_record와 동일한 구조"""
    s = product.get("structured", {})
    return {
        "eval_id": f"eval_{product.get('product_id', 'unknown')}_{persona_idx:02d}",
        "source_product_id": product.get("product_id"),
        "source_product_name": product.get("상품명", ""),
        "source_product_category": product.get("_source_category", ""),
        "source_product_tag": product.get("태그", ""),
        "source_product_brand": product.get("브랜드", ""),
        "persona_info": persona_info,
        "ground_truth": {
            "product_ids": [product.get("product_id")],
            "relevance_grades": {
                product.get("product_id"): 3
            },
        },
        "_reference": {
            "target_user": s.get("target_user", ""),
            "concern": s.get("concern", []),
            "suitable_for": s.get("suitable_for", []),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def generate_persona(
    client: AsyncOpenAI,
    product: dict,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    product_id = product.get("product_id", "unknown")
    prompt = build_reverse_persona_prompt(product)

    _BAD = frozenset("\ufeff\ufffe\uffff")
    prompt = "".join(ch for ch in prompt if (ch >= " " or ch in "\n\t") and ch not in _BAD)

    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[error] {product_id} 페르소나 생성 실패: {e}")
            return None


async def main(output_path: Path, model: str, concurrency: int):
    print(f"\n{'='*60}")
    print(f"hair 상품 페르소나 재생성")
    print(f"  출력: {output_path}")
    print(f"  LLM 모델: {model}")
    print(f"  동시 실행: {concurrency}")
    print(f"  대상 상품: {len(TARGET_PRODUCT_IDS)}개 × {NUM_PERSONAS}페르소나 = {len(TARGET_PRODUCT_IDS)*NUM_PERSONAS}개")
    print(f"{'='*60}\n")

    # 1. 대상 상품 로드
    products = load_hair_products()
    if not products:
        print("대상 상품을 찾을 수 없음. 종료.")
        return
    print(f"로드된 상품: {len(products)}개")
    for p in products:
        s = p.get("structured", {})
        print(f"  [{p['product_id']}] {p.get('상품명','')}  concern={s.get('concern',[])}")
    print()

    # 2. 기존 eval 캐시 로드
    cache = load_eval_cache(output_path)
    print(f"기존 캐시: {len(cache)}개 로드\n")

    # 3. 페르소나 재생성
    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(concurrency)
    total = len(products) * NUM_PERSONAS
    done_count = 0
    success = 0
    new_records: dict[str, dict] = {}

    async def process(product: dict):
        nonlocal done_count, success
        product_id = product.get("product_id")
        for idx in range(NUM_PERSONAS):
            persona = await generate_persona(client, product, model, semaphore)
            done_count += 1
            eval_id = f"eval_{product_id}_{idx:02d}"
            if persona is None:
                print(f"[{done_count}/{total}] [skip] {eval_id} - 페르소나 생성 실패")
                continue
            record = build_eval_record(product, persona, persona_idx=idx)
            new_records[eval_id] = record
            success += 1
            concerns = persona.get("고민 키워드", [])
            print(
                f"[{done_count}/{total}] [done] {eval_id}\n"
                f"         이름: {persona.get('이름','?')}  나이: {persona.get('나이','?')}세  직업: {persona.get('직업','?')}\n"
                f"         고민: {concerns}\n"
                f"         루틴: {str(persona.get('루틴',''))[:80]}"
            )

    await asyncio.gather(*[process(p) for p in products])

    # 4. 캐시 병합 후 전체 재저장
    cache.update(new_records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in cache.values():
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"완료: {success}/{total}개 재생성")
    print(f"전체 캐시: {len(cache)}개 → {output_path}")
    print(f"{'='*60}\n")
    print("※ 다음 단계: eval_query_dataset.jsonl 업데이트 필요")
    print("   python eval/generate_query_dataset.py  (신규 eval_id 자동 추가)")


def parse_args():
    parser = argparse.ArgumentParser(description="hair 상품 페르소나 재생성")
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"출력 eval 데이터셋 경로 (기본값: {DEFAULT_OUTPUT.name})"
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"동시 LLM 호출 수 (기본값: {DEFAULT_CONCURRENCY})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        output_path=Path(args.output),
        model=args.model,
        concurrency=args.concurrency,
    ))
