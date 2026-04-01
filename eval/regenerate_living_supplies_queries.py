"""
living_supplies 상품 쿼리 재생성 스크립트

지정된 product_id에 해당하는 eval 레코드의 검색 쿼리를 재생성하여
eval_query_dataset.jsonl에 덮어씁니다.

사용법:
    python eval/regenerate_living_supplies_queries.py
    python eval/regenerate_living_supplies_queries.py --concurrency 5
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

import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from backend.app.agents.marketing_assistant.services.generate_product_search_query_from_persona import (
    generate_product_search_query_from_persona,
)
from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

_EVAL_DIR      = Path(__file__).parent
DEFAULT_INPUT  = _EVAL_DIR / "synthetic_eval_dataset.jsonl"
DEFAULT_OUTPUT = _EVAL_DIR / "eval_query_dataset.jsonl"
DEFAULT_CONCURRENCY = 5

# 재생성 대상 product_id 목록
TARGET_PRODUCT_IDS = {
    "A20251200019",
    "A20251200025",
    "A20251200026",
    "A20251200027",
    "A20251200031",
    "A20251200265",
    "A20251200266",
    "A20251200268",
    "A20251200271",
    "A20251200275",
}


def load_eval_dataset(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_query_cache(path: Path) -> dict[str, dict]:
    """기존 쿼리 캐시를 {eval_id: entry} 딕셔너리로 로드"""
    cache: dict[str, dict] = {}
    if not path.exists():
        return cache
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    cache[entry["eval_id"]] = entry
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


async def main(input_path: Path, output_path: Path, concurrency: int):
    print(f"\n{'='*60}")
    print(f"living_supplies 쿼리 재생성")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  LLM 모델: {settings.chatgpt_model_name}")
    print(f"  동시 실행: {concurrency}")
    print(f"  대상 상품: {len(TARGET_PRODUCT_IDS)}개")
    print(f"{'='*60}\n")

    # 1. 기존 쿼리 캐시 로드
    cache = load_query_cache(output_path)
    print(f"기존 캐시: {len(cache)}개 로드\n")

    # 2. 재생성 대상 필터링 (source_product_id 기준)
    all_records = load_eval_dataset(input_path)
    targets = [r for r in all_records if r.get("source_product_id") in TARGET_PRODUCT_IDS]
    total = len(targets)

    if total == 0:
        print("재생성 대상 레코드 없음. 종료.")
        return

    # 기존 캐시에 있는 항목 수 표시
    already_cached = sum(1 for r in targets if r["eval_id"] in cache)
    print(f"재생성 대상: {total}개 (기존 캐시 {already_cached}개 덮어쓰기 포함)\n")

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(concurrency)
    done_count = 0
    success = 0
    new_entries: dict[str, dict] = {}

    async def process_one(record: dict):
        nonlocal done_count, success
        eval_id = record["eval_id"]
        persona_info = record["persona_info"]

        async with semaphore:
            try:
                raw = await generate_product_search_query_from_persona(llm, persona_info)
                queries = {
                    "user_need_query":       raw["need"],
                    "user_preference_query": raw["preference"],
                    "retrieval":             raw["retrieval"],
                    "persona":               raw["persona"],
                }
                new_entries[eval_id] = {"eval_id": eval_id, "queries": queries}
                done_count += 1
                success += 1
                print(
                    f"[{done_count}/{total}] [done] {eval_id}\n"
                    f"         need:      {queries['user_need_query']}\n"
                    f"         pref:      {queries['user_preference_query']}\n"
                    f"         retrieval: {queries['retrieval']}\n"
                    f"         persona:   {queries['persona']}"
                )
            except Exception as e:
                done_count += 1
                print(f"[{done_count}/{total}] [error] {eval_id}: {e}")

    await asyncio.gather(*[process_one(r) for r in targets])

    # 3. 캐시에 병합 (대상 eval_id는 새 값으로 교체)
    cache.update(new_entries)

    # 4. 전체 캐시를 다시 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in cache.values():
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"완료: {success}/{total}개 재생성")
    print(f"전체 캐시: {len(cache)}개 → {output_path}")
    print(f"{'='*60}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="living_supplies 쿼리 재생성")
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
