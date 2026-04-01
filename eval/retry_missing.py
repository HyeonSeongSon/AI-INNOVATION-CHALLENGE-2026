"""
누락/실패 eval 레코드 재생성 스크립트

기존 출력 파일을 읽어 생성되지 않은 (product_id, persona_idx) 쌍만 재생성하고
파일에 추가(append)합니다. 기존 레코드는 덮어쓰지 않습니다.

사용법:
    python eval/retry_missing.py
    python eval/retry_missing.py --output eval/synthetic_eval_dataset.jsonl
    python eval/retry_missing.py --model gpt-4o-mini --num-personas 3
"""
import asyncio
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

# generate_eval_dataset에서 공통 함수/상수 재사용
from generate_eval_dataset import (
    _ROOT,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT,
    MAX_CONCURRENT,
    NUM_PERSONAS,
    load_selected_products,
    generate_persona,
    build_eval_record,
)

load_dotenv(_ROOT / "backend" / "app" / ".env")


async def main(model: str, output_path: Path, num_personas: int = NUM_PERSONAS):
    print(f"\n{'='*60}")
    print(f"누락 레코드 재생성")
    print(f"  대상 파일: {output_path}")
    print(f"  LLM 모델: {model}")
    print(f"  상품당 페르소나: {num_personas}개")
    print(f"{'='*60}\n")

    # 1. 기존 파일에서 이미 생성된 eval_id 수집
    existing_ids: set[str] = set()
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        existing_ids.add(record["eval_id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
    print(f"기존 레코드: {len(existing_ids)}개\n")

    # 2. 전체 상품 로드
    products = load_selected_products()

    # 3. 누락된 (product, idx) 쌍 찾기
    missing: list[tuple[dict, int]] = []
    for product in products:
        product_id = product.get("product_id")
        for idx in range(num_personas):
            eval_id = f"eval_{product_id}_{idx:02d}"
            if eval_id not in existing_ids:
                missing.append((product, idx))

    total = len(missing)
    if total == 0:
        print("누락 레코드 없음. 종료.")
        return

    print(f"누락 레코드: {total}개 → 재생성 시작...\n")

    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    done_count = 0
    success = 0

    async def process_one(product: dict, idx: int, out_file):
        nonlocal done_count, success
        product_id = product.get("product_id")
        persona = await generate_persona(client, product, model, semaphore)
        done_count += 1
        if persona is None:
            print(f"[{done_count}/{total}] [skip] {product_id}_{idx:02d} - 페르소나 생성 실패")
            return
        record = build_eval_record(product, persona, persona_idx=idx)
        out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        out_file.flush()
        success += 1
        print(
            f"[{done_count}/{total}] [done] {product_id}_{idx:02d}"
            f" ({product.get('_source_category')}) → {persona.get('이름', '?')}, {persona.get('나이', '?')}세"
        )

    # 4. append 모드로 누락 레코드만 추가 (기존 내용 보존)
    with open(output_path, "a", encoding="utf-8") as f:
        await asyncio.gather(*[process_one(p, idx, f) for p, idx in missing])

    print(f"\n{'='*60}")
    print(f"완료: {success}/{total}개 추가 → {output_path}")
    print(f"총 레코드: {len(existing_ids) + success}개")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="누락 eval 레코드 재생성")
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"대상 파일 경로 (기본값: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--num-personas", type=int, default=NUM_PERSONAS,
        help=f"상품당 페르소나 수 (기본값: {NUM_PERSONAS})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        model=args.model,
        output_path=Path(args.output),
        num_personas=args.num_personas,
    ))
