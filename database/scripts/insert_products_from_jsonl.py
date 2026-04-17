"""
v3 JSONL 파일에서 직접 PostgreSQL에 상품 데이터 삽입

대상 파일 (data/ 디렉토리):
  v3_product_data_rewritten_beauty_tool.jsonl
  v3_product_data_rewritten_color_tone.jsonl
  v3_product_data_rewritten_fragrance_body.jsonl
  v3_product_data_rewritten_hair.jsonl
  v3_product_data_rewritten_inner_beauty.jsonl
  v3_product_data_rewritten_living_supplies.jsonl
  v3_product_data_rewritten_skincare.jsonl

v3 필드 매핑:
  카테고리  → category   (대분류)
  태그      → tag        (중분류)
  서브태그  → sub_tag    (소분류)
  structured (without _original_semantic) → product_details
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import json
from app.core.database import get_db
from app.core.models import Product
from sqlalchemy.exc import IntegrityError


# ── 대상 파일 목록 ────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent.parent / "data"

SOURCE_FILES = [
    DATA_DIR / "v3_product_data_rewritten_beauty_tool.jsonl",
    DATA_DIR / "v3_product_data_rewritten_color_tone.jsonl",
    DATA_DIR / "v3_product_data_rewritten_fragrance_body.jsonl",
    DATA_DIR / "v3_product_data_rewritten_hair.jsonl",
    DATA_DIR / "v3_product_data_rewritten_inner_beauty.jsonl",
    DATA_DIR / "v3_product_data_rewritten_living_supplies.jsonl",
    DATA_DIR / "v3_product_data_rewritten_skincare.jsonl",
]

# structured 필드에서 제외할 키
EXCLUDED_STRUCTURED_KEYS = {"_original_semantic"}


def _safe_int(value) -> int | None:
    """문자열 "None" 또는 None을 None으로, 나머지는 int 변환"""
    if value is None or str(value).strip().lower() == "none":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> float | None:
    if value is None or str(value).strip().lower() == "none":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _clean_structured(structured: dict | None) -> dict | None:
    """structured 필드에서 제외 키 제거 후 반환"""
    if not isinstance(structured, dict):
        return None
    return {k: v for k, v in structured.items() if k not in EXCLUDED_STRUCTURED_KEYS}


def _load_all_products() -> list[dict]:
    """SOURCE_FILES 전체에서 레코드 로드. 파일이 없으면 경고 후 건너뜀."""
    records = []
    for path in SOURCE_FILES:
        if not path.exists():
            print(f"[WARN] 파일 없음, 건너뜀: {path.name}")
            continue
        count_before = len(records)
        with open(path, "rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line.decode("utf-8")))
        print(f"  {path.name}: {len(records) - count_before}개 로드")
    return records


def insert_products_from_jsonl():
    """v3 JSONL 파일 다수에서 상품 데이터를 읽어 PostgreSQL에 삽입"""

    print("=" * 60)
    print("v3 JSONL → PostgreSQL Insert")
    print("=" * 60)

    products_data = _load_all_products()
    if not products_data:
        print("[ERROR] 로드된 데이터가 없습니다. 파일 경로를 확인하세요.")
        return

    print(f"\n총 {len(products_data)}개 상품 로드 완료\n")

    success_count = 0
    skip_count = 0
    error_count = 0

    with next(get_db()) as db:
        for idx, data in enumerate(products_data, 1):
            try:
                persona_tags = data.get("페르소나태그") or {}
                if not isinstance(persona_tags, dict):
                    persona_tags = {}

                product = Product(
                    product_id=data.get("product_id"),
                    vectordb_id=data.get("vectordb_id"),        # OpenSearch 색인 후 채워짐
                    product_name=data.get("상품명", ""),
                    brand=data.get("브랜드"),
                    # 카테고리 계층
                    category=data.get("카테고리"),
                    tag=data.get("태그"),
                    sub_tag=data.get("서브태그"),
                    # 평점/리뷰
                    rating=_safe_float(data.get("별점")),
                    review_count=_safe_int(data.get("리뷰_갯수")) or 0,
                    # 가격
                    original_price=_safe_int(data.get("원가")),
                    discount_rate=_safe_int(data.get("할인율")),
                    sale_price=_safe_int(data.get("판매가")),
                    # 페르소나 매칭 속성
                    skin_type=persona_tags.get("피부타입") or [],
                    concerns=persona_tags.get("고민키워드") or [],
                    preferred_colors=persona_tags.get("선호포인트색상") or [],
                    preferred_ingredients=persona_tags.get("선호성분") or [],
                    avoided_ingredients=persona_tags.get("기피성분") or [],
                    preferred_scents=persona_tags.get("선호향") or [],
                    lifestyle_values=persona_tags.get("가치관") or [],
                    exclusive_product=(
                        ", ".join(persona_tags["전용제품"])
                        if persona_tags.get("전용제품")
                        else None
                    ),
                    personal_color=data.get("퍼스널컬러") or [],
                    skin_shades=data.get("피부호수") or persona_tags.get("피부톤번호") or [],
                    # URL / 이미지
                    product_image_url=data.get("상품이미지") or [],
                    product_page_url=data.get("product_url"),
                    # 소개
                    product_comment=data.get("한줄소개"),
                    # 구조화 상품 정보 (_original_semantic 제외)
                    product_details=_clean_structured(data.get("structured")),
                )

                db.add(product)
                success_count += 1

                if idx % 100 == 0:
                    db.commit()
                    print(f"Progress: {idx}/{len(products_data)}")

            except IntegrityError:
                db.rollback()
                skip_count += 1
            except Exception as e:
                db.rollback()
                error_count += 1
                print(f"[ERROR] idx={idx} product_id={data.get('product_id')}: {e}")

        db.commit()

    print()
    print("=" * 60)
    print("완료")
    print("=" * 60)
    print(f"  성공:            {success_count}")
    print(f"  중복 건너뜀:     {skip_count}")
    print(f"  오류:            {error_count}")
    print(f"  전체:            {len(products_data)}")
    print("=" * 60)


if __name__ == "__main__":
    insert_products_from_jsonl()
