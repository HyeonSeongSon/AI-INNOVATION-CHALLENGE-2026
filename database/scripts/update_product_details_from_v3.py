"""
v3 JSONL 파일의 structured 필드를 products 테이블의 product_details 컬럼에 업데이트
- _original_semantic 필드는 제외
- product_id 기준으로 UPDATE (없으면 스킵)
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# .env 로드 (database/.env 기준)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB", "ai_innovation_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres123"),
}

DATA_DIR = Path(__file__).parent.parent.parent / "data"

V3_FILES = [
    "v3_product_data_rewritten_skincare.jsonl",
    "v3_product_data_rewritten_living_supplies.jsonl",
    "v3_product_data_rewritten_inner_beauty.jsonl",
    "v3_product_data_rewritten_hair.jsonl",
    "v3_product_data_rewritten_fragrance_body.jsonl",
    "v3_product_data_rewritten_color_tone.jsonl",
    "v3_product_data_rewritten_beauty_tool.jsonl",
]


def load_records(file_path: Path) -> list[dict]:
    records = []
    with open(file_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [WARN] {file_path.name} line {lineno}: JSON parse error — {e}")
    return records


def build_product_details(record: dict) -> dict | None:
    """structured 필드에서 _original_semantic 제거 후 반환"""
    structured = record.get("structured")
    if not isinstance(structured, dict):
        return None
    return {k: v for k, v in structured.items() if k != "_original_semantic"}


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    total_updated = 0
    total_skipped = 0
    total_no_structured = 0
    total_errors = 0

    for filename in V3_FILES:
        file_path = DATA_DIR / filename
        if not file_path.exists():
            print(f"[SKIP] 파일 없음: {file_path}")
            continue

        records = load_records(file_path)
        print(f"\n[{filename}] {len(records)}개 레코드 처리 중...")

        file_updated = 0
        file_skipped = 0

        for record in records:
            product_id = record.get("product_id")
            if not product_id:
                total_errors += 1
                continue

            product_details = build_product_details(record)
            if product_details is None:
                total_no_structured += 1
                continue

            try:
                cur.execute(
                    """
                    UPDATE products
                    SET product_details = %s
                    WHERE product_id = %s
                    """,
                    (json.dumps(product_details, ensure_ascii=False), product_id),
                )
                if cur.rowcount == 0:
                    # products 테이블에 해당 product_id 없음
                    file_skipped += 1
                    total_skipped += 1
                else:
                    file_updated += 1
                    total_updated += 1
            except Exception as e:
                conn.rollback()
                print(f"  [ERROR] product_id={product_id}: {e}")
                total_errors += 1
                continue

        conn.commit()
        print(f"  → 업데이트: {file_updated}, 스킵(DB 없음): {file_skipped}")

    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print("완료!")
    print(f"  총 업데이트: {total_updated}")
    print(f"  DB에 없음(스킵): {total_skipped}")
    print(f"  structured 없음: {total_no_structured}")
    print(f"  오류: {total_errors}")
    print("=" * 60)


if __name__ == "__main__":
    run()
