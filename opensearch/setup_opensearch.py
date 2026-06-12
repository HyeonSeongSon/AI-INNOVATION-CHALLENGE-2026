"""
OpenSearch 서비스 환경 구축 스크립트

새 환경에서 이 스크립트 하나를 실행하면 서비스 운영에 필요한
모든 인덱스와 파이프라인이 준비됩니다.

실행 순서:
  0. 환경변수 · 데이터 파일 · 연결 사전 확인
  1. hybrid-minmax-pipeline 생성
  2. product_index_v3 색인 (7개 카테고리)
  3. product_v4_* 색인 (5개 필드 인덱스, 멀티벡터)
  4. forbidden_sentences 색인 (금지 표현 문장 KNN 인덱스)

사전 요건:
  - opensearch/.env 에 OPENSEARCH_ADMIN_PASSWORD / OPENSEARCH_HOST /
    OPENSEARCH_PORT / INTERNAL_TOKEN 설정
  - data/ 디렉토리에 v4_product_data_*.jsonl (10개) 존재

부분 실행 옵션:
  --skip-pipeline   search pipeline 생성 건너뜀
  --skip-v4         product_v4_* 색인 건너뜀
  --skip-forbidden  forbidden_sentences 색인 건너뜀
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# opensearch 디렉토리를 sys.path에 추가 (각 모듈 import를 위해)
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from path_utils import get_absolute_path

REQUIRED_ENV_VARS = [
    "OPENSEARCH_ADMIN_PASSWORD",
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "INTERNAL_TOKEN",
]

V4_DATA_FILES = [
    get_absolute_path("data", "v4_product_data_beauty_tool.jsonl"),
    get_absolute_path("data", "v4_product_data_color_tone.jsonl"),
    get_absolute_path("data", "v4_product_data_color_tone_add.jsonl"),
    get_absolute_path("data", "v4_product_data_fragrance_body.jsonl"),
    get_absolute_path("data", "v4_product_data_fragrance_body_add.jsonl"),
    get_absolute_path("data", "v4_product_data_hair.jsonl"),
    get_absolute_path("data", "v4_product_data_inner_beauty.jsonl"),
    get_absolute_path("data", "v4_product_data_inner_beauty_add.jsonl"),
    get_absolute_path("data", "v4_product_data_living_supplies.jsonl"),
    get_absolute_path("data", "v4_product_data_skincare.jsonl"),
]

V4_INDEX_NAMES = [
    "product_v4_combined",
    "product_v4_function_desc",
    "product_v4_attribute_desc",
    "product_v4_target_user",
    "product_v4_spec_feature",
]


# ---------------------------------------------------------------------------
# 사전 확인
# ---------------------------------------------------------------------------

def check_env_vars() -> bool:
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        logger.error("필수 환경변수 누락: %s", ", ".join(missing))
        logger.error("opensearch/.env 파일을 확인하세요. (.env.example 참고)")
        return False
    logger.info("환경변수 확인 완료")
    return True


def check_data_files(files: list[str], label: str) -> bool:
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        logger.error("[%s] 데이터 파일 누락 (%d개):", label, len(missing))
        for f in missing:
            logger.error("  - %s", f)
        return False
    logger.info("[%s] 데이터 파일 확인 완료 (%d개)", label, len(files))
    return True


def get_client():
    """OpenSearch 클라이언트 + 임베딩 모델 초기화. 실패 시 None 반환."""
    from opensearch_hybrid import OpenSearchHybridClient
    logger.info("OpenSearch 연결 중 (임베딩 모델 로드 포함, 수 분 소요될 수 있습니다)...")
    client = OpenSearchHybridClient()
    if not client.client:
        logger.error("OpenSearch 연결 실패 — HOST/PORT/PASSWORD를 확인하세요.")
        return None
    logger.info("OpenSearch 연결 확인 완료")
    return client


# ---------------------------------------------------------------------------
# 각 단계
# ---------------------------------------------------------------------------

def step_create_pipeline(client) -> bool:
    pipeline_id = "hybrid-minmax-pipeline"
    pipeline_body = client._create_search_pipe_line_body()
    ok = client.create_search_pipeline(pipeline_id, pipeline_body)
    if ok:
        logger.info("search pipeline 생성 완료: %s", pipeline_id)
    else:
        logger.error("search pipeline 생성 실패: %s", pipeline_id)
    return ok


def step_index_v3() -> bool:
    from run_indexing_pipeline import run_pipeline
    logger.info("product_index_v3 색인 시작 (7개 카테고리)...")
    return run_pipeline()


def step_index_forbidden_sentences(client) -> bool:
    from index_forbidden_sentences import run_indexing
    logger.info("forbidden_sentences 인덱스 색인 시작...")
    return run_indexing(client=client)


def step_index_v4() -> bool:
    from index_products_v4_multivector import run_indexing, FIELD_NAMES, INDEX_PREFIX
    logger.info("product_v4_* 색인 시작 (5개 필드 인덱스)...")
    try:
        run_indexing(recreate_index=True, client=client)
    except Exception as e:
        logger.error("product_v4_* 색인 중 오류: %s", type(e).__name__)
        return False

    # 동일 client로 문서 수 확인 (추가 인스턴스 생성 없음)
    all_ok = True
    for field in FIELD_NAMES:
        index_name = f"{INDEX_PREFIX}_{field}"
        try:
            count = client.client.count(index=index_name)["count"]
            if count == 0:
                logger.error("[%s] 문서 수 0 — 색인 실패로 판단", index_name)
                all_ok = False
            else:
                logger.info("[%s] 문서 수: %d", index_name, count)
        except Exception:
            logger.error("[%s] 인덱스 조회 실패", index_name)
            all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# 요약 출력
# ---------------------------------------------------------------------------

def print_summary(results: dict[str, bool], elapsed: float) -> None:
    print("\n" + "=" * 60)
    print("OpenSearch 환경 구축 결과")
    print("=" * 60)
    for step, ok in results.items():
        mark = "✅" if ok else "❌"
        print(f"  {mark} {step}")
    print(f"\n총 소요 시간: {elapsed:.1f}초")
    print("=" * 60)
    if all(results.values()):
        print("🎉 모든 인덱스가 성공적으로 구축되었습니다!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"⚠️  실패한 단계: {', '.join(failed)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSearch 서비스 환경 구축")
    parser.add_argument("--skip-pipeline", action="store_true", help="search pipeline 생성 건너뜀")
    parser.add_argument("--skip-v4", action="store_true", help="product_v4_* 색인 건너뜀")
    parser.add_argument("--skip-forbidden", action="store_true", help="forbidden_sentences 색인 건너뜀")
    args = parser.parse_args()

    print("=" * 60)
    print("OpenSearch 서비스 환경 구축 시작")
    print("=" * 60)

    # 사전 확인: 환경변수
    if not check_env_vars():
        sys.exit(1)

    # 사전 확인: 데이터 파일
    data_ok = True
    if not args.skip_v4:
        data_ok &= check_data_files(V4_DATA_FILES, "v4")
    if not data_ok:
        sys.exit(1)

    # 사전 확인: OpenSearch 연결 (pipeline 생성에도 client 재사용)
    client = get_client()
    if not client:
        sys.exit(1)

    results: dict[str, bool] = {}
    start = time.time()

    # Step 1: Search pipeline
    if not args.skip_pipeline:
        results["hybrid-minmax-pipeline"] = step_create_pipeline(client)
        if not results["hybrid-minmax-pipeline"]:
            print_summary(results, time.time() - start)
            sys.exit(1)

    # Step 2: product_v4_*
    if not args.skip_v4:
        t = time.time()
        results["product_v4_*"] = step_index_v4(client)
        logger.info("product_v4_* 완료 (%.1f초)", time.time() - t)

    # Step 4: forbidden_sentences
    if not args.skip_forbidden:
        t = time.time()
        results["forbidden_sentences"] = step_index_forbidden_sentences(client)
        logger.info("forbidden_sentences 완료 (%.1f초)", time.time() - t)
        if not results["forbidden_sentences"]:
            print_summary(results, time.time() - start)
            sys.exit(1)

    print_summary(results, time.time() - start)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
