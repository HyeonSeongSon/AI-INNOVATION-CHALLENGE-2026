"""
# 기본 실행 (해당 ID의 데이터를 새로 만들어 덮어씌움)
python -m eval.v4.v4_retry_eval_dataset_persona 상품id
"""

import asyncio
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


from .v4_generate_eval_dataset_persona import (
    load_products, CATEGORY_MAP, DATA_FILES, DEFAULT_MODEL, 
    DEFAULT_OUTPUT, MAX_CONCURRENT, build_reverse_persona_prompt, 
    generate_persona, build_eval_record, _ROOT
)

load_dotenv(_ROOT / "backend" / "app" / ".env")

def load_specific_product(product_id: str) -> dict | None:
    """모든 카테고리 파일을 뒤져서 특정 product_id를 가진 상품을 찾습니다."""
    for category, path in DATA_FILES.items():
        if not path.exists():
            continue
        
        with open(path, encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                if item.get("product_id") == product_id:
                    item["_source_category"] = category
                    return item
    return None

async def main(product_id: str, model: str, output_path: Path, num_personas: int):
    print(f"\n{'='*60}")
    print(f"특정 상품 페르소나 재생성: {product_id}")
    print(f"  출력 파일: {output_path.name}")
    print(f"{'='*60}\n")

    # 1. 상품 정보 로드
    product = load_specific_product(product_id)
    if not product:
        print(f"[error] 상품 ID '{product_id}'를 데이터 파일에서 찾을 수 없습니다.")
        return

    # 2. 기존 데이터 로드 및 해당 ID 제거 (덮어쓰기 준비)
    all_records = []
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    # 현재 수정하려는 product_id와 다른 것들만 유지
                    if record.get("source_product_id") != product_id:
                        all_records.append(record)
        print(f"[info] 기존 파일에서 {product_id}와 관련된 이전 레코드를 제외한 {len(all_records)}개를 로드했습니다.")

    # 3. 새로운 페르소나 생성
    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    new_records = []

    print(f"[gen] {product_id}에 대해 {num_personas}개의 새로운 페르소나 생성 중...")
    
    tasks = []
    for idx in range(num_personas):
        tasks.append(generate_persona(client, product, model, semaphore))
    
    results = await asyncio.gather(*tasks)

    for idx, persona in enumerate(results):
        if persona:
            record = build_eval_record(product, persona, persona_idx=idx)
            new_records.append(record)
            print(f"  - 생성 완료 ({idx+1}/{num_personas}): {persona.get('나이', '?')}세")
        else:
            print(f"  - 생성 실패 ({idx+1}/{num_personas})")

    # 4. 파일 업데이트 (전체 다시 쓰기)
    all_records.extend(new_records)
    
    # eval_id 기준으로 정렬 (선택 사항)
    all_records.sort(key=lambda x: x.get("eval_id", ""))

    with open(output_path, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n[success] {len(new_records)}개의 레코드가 업데이트되었습니다. -> {output_path}")

def parse_args():
    parser = argparse.ArgumentParser(description="특정 상품 ID의 페르소나 재생성 및 덮어쓰기")
    parser.add_argument("product_id", type=str, help="재생성할 상품의 product_id")
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"업데이트할 파일 경로 (기본값: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--num-personas", type=int, default=1,
        help="상품당 생성할 페르소나 수 (기본값: 1)"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        product_id=args.product_id,
        model=args.model,
        output_path=Path(args.output),
        num_personas=args.num_personas,
    ))