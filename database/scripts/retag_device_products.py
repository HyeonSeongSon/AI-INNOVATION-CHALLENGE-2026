"""
product_data_for_db.jsonl에서 잘못 태깅된 디바이스/스칼프 계열 상품 67개의 '태그'를
data/product_data_251231_validated.jsonl의 '서브태그'(검증된 값, tag_valid=true)로 되돌린다.

배경:
  전동마사지기/홈뷰티디바이스/에어케어가전/헤어드라이기/고데기/청소기 상품 57개가
  product_data_for_db.jsonl에서 전부 "뷰티디바이스"로 뭉뚱그려 태깅돼 있었고,
  두피트리트먼트 9개는 트리트먼트&팩/에센스&세럼&오일/마스크&팩 등 인접 스킨케어
  태그로 흩어져 있었다. 원본 검증 데이터(product_data_251231_validated.jsonl,
  tag_valid=true)에는 이 상품들의 정확한 서브태그가 남아있어 그걸로 복원한다.
  (product_id는 두 파일에 전부 공통 — 상품이 없는 게 아니라 태그만 잘못됐던 것.)

사용법:
    python retag_device_products.py            # product_data_for_db.jsonl만 수정
    python retag_device_products.py --update-db # 위 + 라이브 DB의 products.tag도 UPDATE
"""

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
VALIDATED_FILE = _ROOT / "data" / "product_data_251231_validated.jsonl"
DB_DATA_FILE = _ROOT / "database" / "data" / "product_data_for_db.jsonl"

TARGET_SUBTAGS = {
    "고데기", "청소기", "헤어드라이기", "전동마사지기",
    "홈뷰티디바이스", "에어케어가전", "두피트리트먼트",
}


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_correct_tags() -> dict[str, str]:
    """product_id -> 검증된 서브태그(TARGET_SUBTAGS 중 하나)."""
    correct: dict[str, str] = {}
    for rec in load_jsonl(VALIDATED_FILE):
        sub_tag = rec.get("서브태그")
        if sub_tag in TARGET_SUBTAGS:
            correct[rec["product_id"]] = sub_tag
    return correct


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-db", action="store_true", help="라이브 Postgres의 products.tag도 갱신")
    args = parser.parse_args()

    correct_tags = build_correct_tags()
    print(f"보정 대상 product_id: {len(correct_tags)}건")

    rows = load_jsonl(DB_DATA_FILE)
    changed = []
    for row in rows:
        pid = row.get("product_id")
        if pid in correct_tags and row.get("태그") != correct_tags[pid]:
            changed.append((pid, row.get("태그"), correct_tags[pid]))
            row["태그"] = correct_tags[pid]

    print(f"{DB_DATA_FILE.name} 중 실제로 값이 바뀐 행: {len(changed)}건")
    for pid, old, new in changed[:10]:
        print(f"  {pid}: {old!r} -> {new!r}")
    if len(changed) > 10:
        print(f"  ... 외 {len(changed) - 10}건")

    with open(DB_DATA_FILE, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"저장 완료: {DB_DATA_FILE}")

    if args.update_db:
        import psycopg2
        from dotenv import load_dotenv
        import os

        load_dotenv(_ROOT / "database" / ".env")
        conn = psycopg2.connect(
            host="localhost", port=5432,
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
        cur = conn.cursor()
        updated = 0
        for pid, _old, new in changed:
            cur.execute("UPDATE products SET tag = %s WHERE product_id = %s", (new, pid))
            updated += cur.rowcount
        conn.commit()
        print(f"DB UPDATE 완료: {updated}행")
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
