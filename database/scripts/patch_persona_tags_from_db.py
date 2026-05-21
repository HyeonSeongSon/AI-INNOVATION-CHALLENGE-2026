"""
products 테이블에서 페르소나 태그 정보를 읽어 JSONL 파일에 역패치

대상 파일:
  data/v3_product_data_structured_color_tone_add.jsonl
  data/v3_product_data_structured_inner_beauty_add.jsonl
  data/v3_product_data_structured_fragrance_body_add.jsonl

로직:
  JSONL의 '상품명' == products.product_name 으로 매칭
  DB 페르소나 필드 → '페르소나태그' 키로 변환 후 JSONL 레코드에 추가
  기존 '페르소나태그' 필드가 있으면 DB 값으로 덮어씀
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import json

from app.core.database import get_db
from app.core.models import Product
from sqlalchemy import select

DATA_DIR = Path(__file__).parent.parent.parent / "data"

TARGET_FILES = [
    DATA_DIR / "v3_product_data_structured_color_tone_add.jsonl",
    DATA_DIR / "v3_product_data_structured_inner_beauty_add.jsonl",
    DATA_DIR / "v3_product_data_structured_fragrance_body_add.jsonl",
]


def _to_persona_tag(product: Product) -> dict:
    """Product ORM 행 → 페르소나태그 dict"""
    exclusive = []
    if product.exclusive_product:
        exclusive = [s.strip() for s in product.exclusive_product.split(",") if s.strip()]

    return {
        "피부타입": list(product.skin_type or []),
        "고민키워드": list(product.concerns or []),
        "선호포인트색상": list(product.preferred_colors or []),
        "선호성분": list(product.preferred_ingredients or []),
        "기피성분": list(product.avoided_ingredients or []),
        "선호향": list(product.preferred_scents or []),
        "가치관": list(product.lifestyle_values or []),
        "전용제품": exclusive,
    }


def _has_persona_data(tag: dict) -> bool:
    """모든 값이 비어있으면 False"""
    return any(tag.values())


def _load_db_persona_map(db) -> dict[str, dict]:
    """상품명 → 페르소나태그 dict 맵 반환"""
    rows = db.execute(select(Product)).scalars().all()
    result: dict[str, dict] = {}
    for row in rows:
        name = row.product_name
        if name:
            result[name] = _to_persona_tag(row)
    print(f"  DB에서 {len(result)}개 상품 로드")
    return result


def _patch_file(path: Path, persona_map: dict[str, dict]) -> None:
    if not path.exists():
        print(f"  [WARN] 파일 없음, 건너뜀: {path.name}")
        return

    records: list[dict] = []
    with open(path, "rb") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line.decode("utf-8")))

    matched = 0
    for rec in records:
        name = rec.get("상품명", "")
        if name in persona_map:
            tag = persona_map[name]
            if _has_persona_data(tag):
                rec["페르소나태그"] = tag
                matched += 1

    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"  {path.name}: {len(records)}개 중 {matched}개 패치 완료")


def main():
    print("=" * 60)
    print("JSONL 페르소나태그 역패치 (DB → JSONL)")
    print("=" * 60)

    with next(get_db()) as db:
        persona_map = _load_db_persona_map(db)

    print()
    for path in TARGET_FILES:
        _patch_file(path, persona_map)

    print()
    print("완료")


if __name__ == "__main__":
    main()
