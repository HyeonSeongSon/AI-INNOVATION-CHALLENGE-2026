"""
스킨케어 카테고리 쿼리 재생성 스크립트

eval/v4_synthetic_eval_dataset.jsonl에서 source_product_category == "skincare" 인
레코드만 필터링하여 검색 쿼리를 재생성하고
eval/v4/v4_retry_skincare_query.jsonl에 저장합니다.

사용법:
    python eval/v4/v4_retry_skincare_query.py
    python eval/v4/v4_retry_skincare_query.py --concurrency 5
"""
import asyncio
import json
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

from eval.v4.v4_generate_query_prompt import build_generate_query_prompt
from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

_EVAL_DIR      = Path(__file__).parent
DEFAULT_INPUT  = _EVAL_DIR.parent / "v4_synthetic_eval_dataset.jsonl"
DEFAULT_OUTPUT = _EVAL_DIR / "v4_retry_skincare_query.jsonl"
DEFAULT_CONCURRENCY = 5
TARGET_CATEGORY = "skincare"


def load_eval_dataset(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def main(input_path: Path, output_path: Path, concurrency: int):
    print(f"\n{'='*60}")
    print(f"스킨케어 검색 쿼리 재생성")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  카테고리: {TARGET_CATEGORY}")
    print(f"  LLM 모델: {settings.chatgpt_model_name}")
    print(f"  동시 실행: {concurrency}")
    print(f"{'='*60}\n")

    # 1. 이미 생성된 eval_id 수집 (재실행 시 중복 방지)
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
    if existing_ids:
        print(f"기존 레코드: {len(existing_ids)}개 (스킵)\n")

    # 2. 스킨케어 카테고리만 필터링 후 처리 대상 선별
    all_records = load_eval_dataset(input_path)
    skincare_records = [
        r for r in all_records
        if r.get("source_product_category") == TARGET_CATEGORY
    ]
    targets = [r for r in skincare_records if r["eval_id"] not in existing_ids]
    total = len(targets)

    print(f"전체 스킨케어 레코드: {len(skincare_records)}개")

    if total == 0:
        print("모든 스킨케어 레코드가 이미 생성됨. 종료.")
        return

    print(f"생성 대상: {total}개\n")

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(concurrency)
    done_count = 0
    success = 0

    async def process_one(record: dict, out_file):
        nonlocal done_count, success
        eval_id = record["eval_id"]
        persona_info = record["persona_info"]

        async with semaphore:
            try:
                prompt = build_generate_query_prompt(persona_info)
                raw = await llm.ainvoke(prompt)
                parsed = json.loads(raw.content)
                queries = {
                    "user_need_query":       parsed["need"],
                    "user_preference_query": parsed["preference"],
                    "retrieval":             parsed["retrieval"],
                    "persona":               parsed["persona"],
                }
                entry = {"eval_id": eval_id, "queries": queries}
                out_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                out_file.flush()
                done_count += 1
                success += 1
                print(f"[{done_count}/{total}] [done] {eval_id}")
            except Exception as e:
                done_count += 1
                print(f"[{done_count}/{total}] [error] {eval_id}: {e}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        await asyncio.gather(*[process_one(r, f) for r in targets])

    print(f"\n{'='*60}")
    print(f"완료: {success}/{total}개 생성 → {output_path}")
    print(f"총 레코드: {len(existing_ids) + success}개")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="스킨케어 카테고리 검색 쿼리 재생성")
    parser.add_argument(
        "--input", type=str, default=str(DEFAULT_INPUT),
        help=f"입력 eval 데이터셋 경로 (기본값: {DEFAULT_INPUT.name})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"출력 쿼리 데이터셋 경로 (기본값: {DEFAULT_OUTPUT.name})"
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"동시 LLM 호출 수 (기본값: {DEFAULT_CONCURRENCY})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        input_path=Path(args.input),
        output_path=Path(args.output),
        concurrency=args.concurrency,
    ))
