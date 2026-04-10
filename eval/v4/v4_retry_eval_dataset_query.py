"""
python v4_update_query_by_id.py 상품ID_1 상품ID_2 상품ID_3
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

_EVAL_DIR = Path(__file__).parent
DEFAULT_INPUT = _EVAL_DIR.parent / "v4_synthetic_eval_dataset.jsonl"
DEFAULT_OUTPUT = _EVAL_DIR / "v4_eval_query_dataset.jsonl"

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def save_jsonl(path: Path, data: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

async def update_query_by_id(eval_ids: list[str], input_path: Path, output_path: Path):
    print(f"\n{'='*60}")
    print(f"특정 ID 쿼리 업데이트 모드")
    print(f"  대상 IDs: {eval_ids}")
    print(f"  입력 소스: {input_path}")
    print(f"  대상 파일: {output_path}")
    print(f"{'='*60}\n")

    # 1. 원본 데이터셋 로드 (persona_info를 가져오기 위함)
    source_records_list = load_jsonl(input_path)
    all_source_records = {r["eval_id"]: r for r in source_records_list}
    # source_product_id -> [eval_id, ...] 역방향 인덱스
    product_id_index: dict[str, list[str]] = {}
    for r in source_records_list:
        pid = r.get("source_product_id", "")
        product_id_index.setdefault(pid, []).append(r["eval_id"])

    # 2. 기존 결과 파일 로드 (교체 대상)
    existing_results = load_jsonl(output_path)
    # 조회를 쉽게 하기 위해 dict로 변환 {eval_id: record}
    results_map = {r["eval_id"]: r for r in existing_results}

    llm = get_llm(settings.chatgpt_model_name, temperature=0)

    # eval_id 또는 source_product_id 모두 허용
    resolved_eval_ids: list[str] = []
    for target_id in eval_ids:
        if target_id in all_source_records:
            resolved_eval_ids.append(target_id)
        elif target_id in product_id_index:
            matched = product_id_index[target_id]
            print(f"[Info] {target_id}는 source_product_id로 인식 → eval_id: {matched}")
            resolved_eval_ids.extend(matched)
        else:
            print(f"[Skip] {target_id}: 원본 데이터셋에 존재하지 않는 ID입니다.")

    for target_id in resolved_eval_ids:
        print(f"[*] {target_id} 쿼리 생성 중...")
        record = all_source_records[target_id]
        persona_info = record["persona_info"]

        try:
            prompt = build_generate_query_prompt(persona_info)
            raw = await llm.ainvoke(prompt)
            parsed = json.loads(raw.content)
            
            new_queries = {
                "user_need_query":      parsed["need"],
                "user_preference_query":  parsed["preference"],
                "retrieval":              parsed["retrieval"],
                "persona":                parsed["persona"],
            }
            
            # 기존 맵 업데이트 (있으면 교체, 없으면 신규 삽입)
            results_map[target_id] = {"eval_id": target_id, "queries": new_queries}
            print(f"[Done] {target_id} 업데이트 완료.")
            
        except Exception as e:
            print(f"[Error] {target_id} 처리 실패: {e}")

    # 3. 전체 데이터를 다시 쓰기 (기존 파일 덮어쓰기)
    # 원본 파일의 순서를 어느정도 유지하고 싶다면 리스트 순서대로 정렬하거나 그대로 저장
    final_data = list(results_map.values())
    save_jsonl(output_path, final_data)
    print(f"\n파일 저장 완료: {output_path} (총 {len(final_data)}개 레코드)")

def parse_args():
    parser = argparse.ArgumentParser(description="특정 ID의 검색 쿼리 업데이트")
    parser.add_argument(
        "ids", nargs="+", help="업데이트할 eval_id 목록 (공백으로 구분)"
    )
    parser.add_argument(
        "--input", type=str, default=str(DEFAULT_INPUT),
        help="원본 데이터셋 경로"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help="업데이트할 결과 파일 경로"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(update_query_by_id(
        eval_ids=args.ids,
        input_path=Path(args.input),
        output_path=Path(args.output)
    ))