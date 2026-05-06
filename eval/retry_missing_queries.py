"""
누락/실패 쿼리 레코드 재생성 스크립트

eval_query_dataset.jsonl에서 빠진 eval_id를 찾아 재생성하고 append합니다.
generate_query_dataset.py 실행 중 에러가 발생한 레코드 복구용.

사용법:
    python eval/retry_missing_queries.py
    python eval/retry_missing_queries.py --input eval/synthetic_eval_dataset.jsonl
    python eval/retry_missing_queries.py --output eval/eval_query_dataset.jsonl
    python eval/retry_missing_queries.py --concurrency 3 --max-retries 5
"""
import asyncio
import json
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

from backend.app.agents.marketing_assistant.services.generate_product_search_query_from_persona import (
    generate_product_search_query_from_persona,
)
from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

_EVAL_DIR      = Path(__file__).parent
DEFAULT_INPUT  = _EVAL_DIR / "synthetic_eval_dataset.jsonl"
DEFAULT_OUTPUT = _EVAL_DIR / "eval_query_dataset.jsonl"
DEFAULT_CONCURRENCY = 3
DEFAULT_MAX_RETRIES = 3


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def generate_with_retry(llm, persona_info: dict, max_retries: int) -> dict | None:
    """재시도 로직 포함 쿼리 생성. 실패 시 None 반환."""
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            raw = await generate_product_search_query_from_persona(llm, persona_info)
            return {
                "user_need_query":       raw["need"],
                "user_preference_query": raw["preference"],
                "retrieval":             raw["retrieval"],
                "persona":               raw["persona"],
            }
        except Exception as e:
            if attempt == max_retries:
                print(f"      [retry {attempt}/{max_retries}] 최종 실패: {e}")
                return None
            print(f"      [retry {attempt}/{max_retries}] 재시도 중... ({e})")
            await asyncio.sleep(delay)
            delay *= 2


async def main(input_path: Path, output_path: Path, concurrency: int, max_retries: int):
    print(f"\n{'='*60}")
    print(f"누락 쿼리 레코드 재생성")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  LLM 모델: {settings.chatgpt_model_name}")
    print(f"  동시 실행: {concurrency}  /  최대 재시도: {max_retries}")
    print(f"{'='*60}\n")

    # 1. 이미 생성된 eval_id 수집
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
    print(f"기존 레코드: {len(existing_ids)}개\n")

    # 2. 누락 레코드 찾기
    all_records = load_jsonl(input_path)
    missing = [r for r in all_records if r["eval_id"] not in existing_ids]
    total = len(missing)

    if total == 0:
        print("누락 레코드 없음. 종료.")
        return

    print(f"누락(실패) 레코드: {total}개 → 재생성 시작...\n")

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(concurrency)
    done_count = 0
    success = 0

    async def process_one(record: dict, out_file):
        nonlocal done_count, success
        eval_id = record["eval_id"]
        persona_info = record["persona_info"]

        async with semaphore:
            done_count += 1
            queries = await generate_with_retry(llm, persona_info, max_retries)
            if queries is None:
                print(f"[{done_count}/{total}] [skip] {eval_id}")
                return
            entry = {"eval_id": eval_id, "queries": queries}
            out_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            out_file.flush()
            success += 1
            print(f"[{done_count}/{total}] [done] {eval_id}")

    # 3. append 모드로 기존 파일에 추가 (기존 내용 보존)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        await asyncio.gather(*[process_one(r, f) for r in missing])

    print(f"\n{'='*60}")
    print(f"완료: {success}/{total}개 추가 → {output_path}")
    print(f"총 레코드: {len(existing_ids) + success}개")
    if success < total:
        print(f"여전히 실패: {total - success}개 (다시 스크립트 실행하거나 --max-retries 늘리기)")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="누락/실패 쿼리 레코드 재생성")
    parser.add_argument("--input",  type=str, default=str(DEFAULT_INPUT))
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        input_path=Path(args.input),
        output_path=Path(args.output),
        concurrency=args.concurrency,
        max_retries=args.max_retries,
    ))
