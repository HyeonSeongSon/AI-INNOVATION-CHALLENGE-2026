"""
database/ 환경 구축 스크립트

`docker compose up -d` 이후 실행하여 현재 환경과 동일한 상태로 구축합니다.

실행:
    cd database
    python setup_db.py

사전 조건:
    - database/.env  설정 완료 (POSTGRES_* 환경변수)
    - opensearch/.env 설정 완료 (OPENSEARCH_* 환경변수, vectordb_id 수집용)
    - 프로젝트 루트 data/ 디렉터리에 v3 JSONL 파일 존재
    - OpenSearch product_v4_* 인덱스 색인 완료

구축 단계:
    Step 1. PostgreSQL 준비 대기 (최대 60초)
    Step 2. products 테이블 데이터 유무 확인
    Step 3. v3 JSONL → PostgreSQL 상품 삽입 (OpenSearch vectordb_id 포함)
"""

import sys
import time
from pathlib import Path

_DB_DIR = Path(__file__).parent
_ROOT = _DB_DIR.parent

# backend 모듈 import를 위한 경로 설정
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_DB_DIR))

from dotenv import load_dotenv

load_dotenv(_DB_DIR / ".env")


# ---------------------------------------------------------------------------
# Step 1: PostgreSQL 준비 대기
# ---------------------------------------------------------------------------

def step_wait_for_postgres(max_retries: int = 30, interval: int = 2) -> bool:
    print("\n[STEP 1] PostgreSQL 준비 대기...")
    print("-" * 60)

    from app.core.database import engine, db_config
    from sqlalchemy import text

    print(f"  대상: {db_config.host}:{db_config.port}/{db_config.database}")

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"  ✅ 연결 성공 (시도 {attempt}/{max_retries})")
            return True
        except Exception:
            print(f"  대기 중... ({attempt}/{max_retries})", end="\r")
            time.sleep(interval)

    print(f"\n  ❌ {max_retries * interval}초 내에 연결 실패")
    print("  PostgreSQL 컨테이너가 정상 실행 중인지 확인하세요:")
    print("    docker compose ps")
    return False


# ---------------------------------------------------------------------------
# Step 2: 기존 데이터 확인
# ---------------------------------------------------------------------------

def step_check_existing_data() -> bool:
    """products 테이블에 데이터가 있으면 True (삽입 건너뜀)."""
    print("\n[STEP 2] 기존 데이터 확인...")
    print("-" * 60)

    from app.core.database import engine
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM products"))
            count = result.scalar()

        if count > 0:
            print(f"  ⚠️  products 테이블에 이미 {count:,}개 데이터가 있습니다.")
            answer = input("  재삽입하시겠습니까? (yes/no): ").strip().lower()
            if answer != "yes":
                print("  건너뜀.")
                return True  # 삽입 불필요
            print("  재삽입을 진행합니다.\n")
            return False

        print(f"  products 테이블 비어 있음 — 삽입 진행")
        return False

    except Exception as e:
        # products 테이블이 없는 경우 (init SQL 미실행 등)
        print(f"  ⚠️  테이블 확인 실패: {type(e).__name__}")
        print("  init/*.sql 이 PostgreSQL 기동 시 실행되었는지 확인하세요.")
        return False


# ---------------------------------------------------------------------------
# Step 3: 상품 데이터 삽입
# ---------------------------------------------------------------------------

def step_insert_products() -> bool:
    print("\n[STEP 3] 상품 데이터 삽입...")
    print("-" * 60)

    try:
        from scripts.insert_products_from_jsonl import insert_products_from_jsonl
        insert_products_from_jsonl()
        return True
    except Exception as e:
        print(f"  ❌ 삽입 실패: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("DATABASE SETUP")
    print("=" * 60)

    results: dict[str, bool] = {}

    # Step 1
    results["postgres_ready"] = step_wait_for_postgres()
    if not results["postgres_ready"]:
        _print_summary(results)
        sys.exit(1)

    # Step 2
    already_done = step_check_existing_data()
    if already_done:
        print("\n✅ 이미 구축된 상태입니다. 종료합니다.")
        sys.exit(0)

    # Step 3
    results["products_inserted"] = step_insert_products()

    _print_summary(results)
    sys.exit(0 if all(results.values()) else 1)


def _print_summary(results: dict[str, bool]) -> None:
    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    labels = {
        "postgres_ready":    "PostgreSQL 연결",
        "products_inserted": "상품 데이터 삽입",
    }
    for key, ok in results.items():
        mark = "✅" if ok else "❌"
        print(f"  {mark} {labels.get(key, key)}")
    print("=" * 60)
    if all(results.values()):
        print("🎉 구축 완료!")
    else:
        failed = [labels.get(k, k) for k, v in results.items() if not v]
        print(f"⚠️  실패: {', '.join(failed)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
