"""
v4 OpenSearch에는 색인됐지만 database/data/product_data_for_db.jsonl에는 없는
"_add" 배치 상품(260개)을 product_data_for_db.jsonl에 append한다.

배경:
  data/v4_product_data_{color_tone,fragrance_body,inner_beauty}_add.jsonl 에는
  product_id + 임베딩용 문장만 있고 상품 메타데이터(이름/브랜드/가격 등)가 없다.
  같은 상품의 메타데이터는 data/v3_product_data_structured_*_add.jsonl 에 있지만
  거긴 반대로 product_id가 없다.

매칭 방법 — 순서 매칭(가정):
  카테고리별로 두 파일의 행 수가 정확히 일치한다(78/46/136개) — 같은 파이프라인에서
  같은 순서로 생성됐다고 보고, N번째 v3_structured 행에 N번째 v4 product_id를 붙인다.
  이건 검증된 매핑이 아니라 정황 증거 기반 가정이다 — 테스트/평가용 DB라 허용.

실행 후 database/scripts/setup_pipeline.py 를 다시 돌리면 이 260개가 삽입된다
(이미 있는 868개는 ON CONFLICT/기존 조회 로직으로 건너뜀).

사용법:
    python backfill_add_batch_products.py
"""

import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = _ROOT / "data"
DB_DATA_FILE = _ROOT / "database" / "data" / "product_data_for_db.jsonl"

# (v3_structured_add 파일, v4_add 파일) 카테고리별 쌍
PAIRS = [
    ("v3_product_data_structured_color_tone_add.jsonl", "v4_product_data_color_tone_add.jsonl"),
    ("v3_product_data_structured_fragrance_body_add.jsonl", "v4_product_data_fragrance_body_add.jsonl"),
    ("v3_product_data_structured_inner_beauty_add.jsonl", "v4_product_data_inner_beauty_add.jsonl"),
]


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_v4_product_ids_in_order(path: Path) -> list[str]:
    """product_id를 파일에 나온 순서 그대로(중복 제거하되 순서 유지) 반환."""
    seen: set[str] = set()
    ids: list[str] = []
    for rec in load_jsonl(path):
        pid = rec.get("product_id")
        if pid and pid not in seen:
            seen.add(pid)
            ids.append(pid)
    return ids


def convert_row(structured: dict, product_id: str) -> dict:
    structured_info = structured.get("structured") or {}
    summary = structured_info.get("summary") or structured_info.get("combined") or ""
    return {
        "product_id": product_id,
        "브랜드": structured.get("브랜드"),
        "상품명": structured.get("상품명", ""),
        "태그": structured.get("tag"),
        "별점": structured.get("별점"),
        "리뷰_갯수": structured.get("리뷰_갯수", 0),
        "원가": structured.get("원가"),
        "할인율": structured.get("할인율"),
        "판매가": structured.get("판매가"),
        "구매자_통계": structured.get("구매자_통계", {}),
        "페르소나태그": {},
        "한줄소개": summary,
        "product_url": structured.get("url"),
        "상품이미지": structured.get("상품이미지", []),
        "상품상세_이미지": structured.get("상품상세_이미지", []),
    }


def main() -> None:
    existing_ids: set[str] = set()
    if DB_DATA_FILE.exists():
        existing_ids = {r.get("product_id") for r in load_jsonl(DB_DATA_FILE)}
    print(f"기존 product_data_for_db.jsonl: {len(existing_ids)}건")

    new_rows: list[dict] = []
    for structured_name, v4_name in PAIRS:
        structured_rows = load_jsonl(DATA_DIR / structured_name)
        v4_ids = load_v4_product_ids_in_order(DATA_DIR / v4_name)

        if len(structured_rows) != len(v4_ids):
            print(
                f"[WARN] {structured_name}({len(structured_rows)}건) != "
                f"{v4_name}({len(v4_ids)}건) — 행 수 불일치, 앞쪽 min()개만 순서 매칭"
            )

        for structured, product_id in zip(structured_rows, v4_ids):
            if product_id in existing_ids:
                continue
            new_rows.append(convert_row(structured, product_id))

        print(f"{structured_name} -> {v4_name}: {len(structured_rows)}건 매칭 시도")

    print(f"\n신규 추가 대상: {len(new_rows)}건")

    if new_rows:
        with open(DB_DATA_FILE, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"저장 완료: {DB_DATA_FILE}")

    total = len(existing_ids) + len(new_rows)
    print(f"최종 예상 건수: {total}")


if __name__ == "__main__":
    main()
