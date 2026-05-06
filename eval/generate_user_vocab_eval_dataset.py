"""
사용자 어휘 기반 eval 쿼리 데이터셋 생성 스크립트

1. test_products_selected.jsonl에서 카테고리별 5개 상품 랜덤 추출
2. synthetic_eval_dataset.jsonl에서 상품 ID별 중복 없이 eval 레코드 1개 추출
3. generate_user_vocab_search_query_prompt.py 프롬프트로 검색 쿼리 생성
4. 결과를 user_vocab_eval_query_dataset.jsonl에 저장
"""
import asyncio
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm
from backend.app.agents.marketing_assistant.prompts.classify_product_type_prompt import (
    build_classify_product_type_prompt,
)
from backend.app.agents.marketing_assistant.prompts.generate_user_vocab_search_query_prompt import (
    build_generate_user_vocab_product_search_query_from_persona_prompt,
)

_EVAL_DIR         = Path(__file__).parent
_DATA_DIR         = _ROOT / "data"
PRODUCTS_FILE     = _DATA_DIR / "test_products_selected.jsonl"
EVAL_DATASET_FILE = _EVAL_DIR / "synthetic_eval_dataset.jsonl"
OUTPUT_FILE       = _EVAL_DIR / "user_vocab_eval_query_dataset.jsonl"

SAMPLES_PER_CATEGORY = 5
CONCURRENCY = 5
RANDOM_SEED = 42


# ── 데이터 로드 ──────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def select_product_ids(products: list[dict], n: int, seed: int) -> list[str]:
    """카테고리별 n개 랜덤 추출 후 product_id 반환"""
    rng = random.Random(seed)
    by_category: dict[str, list[str]] = defaultdict(list)
    for p in products:
        cat = p.get("카테고리", "")
        by_category[cat].append(p["product_id"])

    selected: list[str] = []
    print(f"\n{'카테고리':<12} {'전체':>4}  {'추출':>4}  상품 ID 샘플")
    print("-" * 70)
    for cat, ids in sorted(by_category.items()):
        picked = rng.sample(ids, min(n, len(ids)))
        selected.extend(picked)
        print(f"{cat:<12} {len(ids):>4}개  {len(picked):>4}개  {picked[:3]}")

    print(f"\n총 추출 상품: {len(selected)}개\n")
    return selected


def pick_eval_records(eval_records: list[dict], product_ids: list[str], seed: int) -> list[dict]:
    """product_id별 eval 레코드 1개 랜덤 추출 (중복 없음)"""
    rng = random.Random(seed)
    by_product: dict[str, list[dict]] = defaultdict(list)
    for r in eval_records:
        by_product[r["source_product_id"]].append(r)

    picked: list[dict] = []
    missing: list[str] = []
    for pid in product_ids:
        records = by_product.get(pid, [])
        if records:
            picked.append(rng.choice(records))
        else:
            missing.append(pid)

    if missing:
        print(f"[경고] eval 레코드 없는 상품 ID: {missing}")

    return picked


# ── 쿼리 생성 ─────────────────────────────────────────────────────────────────

async def generate_queries(llm, persona_info: dict) -> dict:
    # Stage 1: 품목 분류
    classify_prompt = build_classify_product_type_prompt(persona_info)
    classify_response = await llm.ainvoke(classify_prompt)
    product_type = json.loads(classify_response.content)["product_type"]

    # Stage 2: 쿼리 생성
    query_prompt = build_generate_user_vocab_product_search_query_from_persona_prompt(
        persona_info, product_type
    )
    query_response = await llm.ainvoke(query_prompt)
    result = json.loads(query_response.content)
    result["_product_type"] = product_type
    return result


async def main():
    print("=" * 60)
    print("사용자 어휘 eval 쿼리 데이터셋 생성")
    print("=" * 60)
    print(f"  상품 파일:  {PRODUCTS_FILE.name}")
    print(f"  eval 파일:  {EVAL_DATASET_FILE.name}")
    print(f"  출력 파일:  {OUTPUT_FILE.name}")
    print(f"  카테고리당 추출: {SAMPLES_PER_CATEGORY}개")
    print(f"  LLM 모델:   {settings.chatgpt_model_name}")
    print(f"  동시 실행:  {CONCURRENCY}")
    print(f"  랜덤 시드:  {RANDOM_SEED}")

    # 1. 상품 로드 및 카테고리별 랜덤 추출
    products = load_jsonl(PRODUCTS_FILE)
    selected_ids = select_product_ids(products, SAMPLES_PER_CATEGORY, RANDOM_SEED)

    # 2. eval 레코드 추출 (상품 ID별 1개)
    eval_records = load_jsonl(EVAL_DATASET_FILE)
    target_records = pick_eval_records(eval_records, selected_ids, RANDOM_SEED)
    total = len(target_records)
    print(f"쿼리 생성 대상: {total}개 레코드\n")

    # 3. 쿼리 생성
    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = []
    done = 0

    async def process_one(record: dict):
        nonlocal done
        eval_id = record["eval_id"]
        pid     = record["source_product_id"]
        cat     = record.get("source_product_category", "")

        async with semaphore:
            try:
                raw = await generate_queries(llm, record["persona_info"])
                product_type = raw.pop("_product_type", "")
                queries = {
                    "user_need_query":       raw["need"],
                    "user_preference_query": raw["preference"],
                    "retrieval":             raw["retrieval"],
                    "persona":               raw["persona"],
                }
                entry = {
                    "eval_id":                  eval_id,
                    "source_product_id":        pid,
                    "source_product_name":      record.get("source_product_name", ""),
                    "source_product_category":  cat,
                    "source_product_tag":       record.get("source_product_tag", ""),
                    "persona_info":             record["persona_info"],
                    "classified_product_type":  product_type,
                    "queries":                  queries,
                    "ground_truth":             record.get("ground_truth", []),
                }
                results.append(entry)
                done += 1
                print(
                    f"[{done:>2}/{total}] [{cat}] {pid}\n"
                    f"         [분류] {product_type}\n"
                    f"         need:      {queries['user_need_query']}\n"
                    f"         pref:      {queries['user_preference_query']}\n"
                    f"         retrieval: {queries['retrieval']}\n"
                    f"         persona:   {queries['persona']}\n"
                )
            except Exception as e:
                done += 1
                print(f"[{done:>2}/{total}] [오류] {eval_id} ({pid}): {e}")

    await asyncio.gather(*[process_one(r) for r in target_records])

    # 4. 저장
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 60}")
    print(f"완료: {len(results)}/{total}개 생성 → {OUTPUT_FILE}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
