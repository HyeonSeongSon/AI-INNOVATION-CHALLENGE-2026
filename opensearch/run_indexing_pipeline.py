"""
전체 카테고리 OpenSearch 색인 파이프라인

실행 순서:
  1. skincare  — 인덱스 생성 (recreate_index=True)
  2. color_tone
  3. hair
  4. nail
  5. fragrance_body
  6. inner_beauty
  7. beauty_tool

skincare가 반드시 먼저 실행되어야 합니다 (인덱스를 생성하기 때문).
이후 카테고리들은 기존 인덱스에 매핑을 추가한 뒤 문서를 색인합니다.
"""
import sys
import os
import logging
import time

# opensearch 디렉터리를 path에 추가 (각 모듈 import를 위해)
_OPENSEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _OPENSEARCH_DIR not in sys.path:
    sys.path.insert(0, _OPENSEARCH_DIR)

from path_utils import get_absolute_path

from index_products_skincare import index_products_to_opensearch
from index_products_color_tone import index_color_tone_to_opensearch
from index_products_hair import index_hair_to_opensearch
from index_products_living_supplies import index_living_supplies_to_opensearch
from index_products_fragrance_body import index_fragrance_body_to_opensearch
from index_products_inner_beauty import index_inner_beauty_to_opensearch
from index_products_beauty_tool import index_beauty_tool_to_opensearch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

INDEX_NAME = "product_index_v2"

PIPELINE_STEPS = [
    {
        "name": "스킨케어",
        "func": index_products_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_skincare.jsonl"),
        "recreate_index": True,   # 인덱스 생성
    },
    {
        "name": "뷰티툴",
        "func": index_beauty_tool_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_beauty_tool.jsonl"),
        "recreate_index": False,
    },
    {
        "name": "색조",
        "func": index_color_tone_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_color_tone.jsonl"),
        "recreate_index": False,
    },
    {
        "name": "헤어",
        "func": index_hair_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_hair.jsonl"),
        "recreate_index": False,
    },
    {
        "name": "생활도구",
        "func": index_living_supplies_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_living_supplies.jsonl"),
    },
    {
        "name": "향수/바디",
        "func": index_fragrance_body_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_fragrance_body.jsonl"),
        "recreate_index": False,
    },
    {
        "name": "이너뷰티",
        "func": index_inner_beauty_to_opensearch,
        "jsonl": get_absolute_path("data", "v2_product_data_structured_inner_beauty.jsonl"),
        "recreate_index": False,
    },
]


def run_pipeline():
    total = len(PIPELINE_STEPS)
    results = []

    print("=" * 60)
    print(f"OpenSearch 색인 파이프라인 시작 — 총 {total}개 카테고리")
    print(f"인덱스: {INDEX_NAME}")
    print("=" * 60)

    pipeline_start = time.time()

    for i, step in enumerate(PIPELINE_STEPS, 1):
        name = step["name"]
        print(f"\n[{i}/{total}] {name} 색인 시작...")
        step_start = time.time()

        kwargs = {"jsonl_file_path": step["jsonl"], "index_name": INDEX_NAME}
        if "recreate_index" in step:
            kwargs["recreate_index"] = step["recreate_index"]
        success = step["func"](**kwargs)

        elapsed = time.time() - step_start
        status = "성공" if success else "실패"
        print(f"[{i}/{total}] {name} {status} ({elapsed:.1f}초)")
        results.append((name, success))

        if not success:
            print(f"\n'{name}' 색인 실패로 파이프라인을 중단합니다.")
            break

    total_elapsed = time.time() - pipeline_start

    print("\n" + "=" * 60)
    print("파이프라인 결과 요약")
    print("=" * 60)
    for name, success in results:
        mark = "[성공]" if success else "[실패]"
        print(f"  {mark} {name}")

    succeeded = sum(1 for _, s in results if s)
    failed = len(results) - succeeded
    print(f"\n총 {len(results)}개 중 {succeeded}개 성공, {failed}개 실패")
    print(f"총 소요 시간: {total_elapsed:.1f}초")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
