"""
EC2 배포용 상품 데이터 시더 — 비대화형, 멱등성 보장

사용법:
    /opt/db-api/venv/bin/python /opt/db-api/seed_products.py

전제 조건:
    - /opt/db-api/.env 에 POSTGRES_* 환경변수 설정
    - /opt/data/ 에 v3 JSONL 파일 존재 (data.tar.gz → /opt/ 압축 해제)

동작:
    - products 테이블에 데이터가 있으면 즉시 종료 (멱등)
    - 없으면 JSONL 파일에서 읽어 PostgreSQL에 삽입
    - vectordb_id는 NULL로 삽입 (OpenSearch 색인 후 별도 업데이트 필요)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# /opt/db-api 를 sys.path 앞에 추가 — core.* 임포트 보장
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv

load_dotenv(_HERE / ".env")

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# data/ 위치: /opt/db-api/../data = /opt/data
DATA_DIR = Path(os.getenv("PRODUCT_DATA_DIR", str(_HERE.parent / "data")))

SOURCE_FILES = [
    "v3_product_data_rewritten_beauty_tool.jsonl",
    "v3_product_data_rewritten_color_tone.jsonl",
    "v3_product_data_structured_color_tone_add.jsonl",
    "v3_product_data_rewritten_fragrance_body.jsonl",
    "v3_product_data_structured_fragrance_body_add.jsonl",
    "v3_product_data_rewritten_hair.jsonl",
    "v3_product_data_rewritten_inner_beauty.jsonl",
    "v3_product_data_structured_inner_beauty_add.jsonl",
    "v3_product_data_rewritten_living_supplies.jsonl",
    "v3_product_data_rewritten_skincare.jsonl",
]

_CATEGORY_CODE: dict[str, str] = {
    "스킨케어": "S", "색조": "C", "헤어": "H", "향수/바디": "F",
    "이너뷰티": "I", "생활도구": "L", "뷰티툴": "B",
}
_EXCLUDED_STRUCTURED_KEYS = {"_original_semantic"}


def _make_product_id(category: str | None) -> str:
    code = _CATEGORY_CODE.get(category or "", "X")
    return f"{code}{datetime.now().strftime('%Y%m')}{uuid4().hex[:6].upper()}"


def _safe_int(value) -> int | None:
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


def main() -> None:
    from core.database import engine, get_db
    from core.models import Product

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()

    print(f"[seed] Products in DB: {count}")
    if count > 0:
        print("[seed] Already seeded, skipping.")
        return

    records: list[dict] = []
    for fname in SOURCE_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"[seed] WARN: missing {path}")
            continue
        before = len(records)
        with open(path, "rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line.decode("utf-8")))
        print(f"[seed] {fname}: {len(records) - before} records")

    if not records:
        print(f"[seed] ERROR: no JSONL files found in {DATA_DIR}")
        sys.exit(1)

    print(f"[seed] Inserting {len(records)} products...")
    success = skip = error = 0

    with next(get_db()) as db:
        for idx, data in enumerate(records, 1):
            try:
                persona_tags = data.get("페르소나태그") or {}
                if not isinstance(persona_tags, dict):
                    persona_tags = {}

                category  = data.get("카테고리") or data.get("category")
                tag       = data.get("태그")     or data.get("tag")
                sub_tag   = data.get("서브태그") or data.get("sub_tag")
                page_url  = data.get("product_url") or data.get("url")
                product_id = data.get("product_id") or _make_product_id(category)

                structured = data.get("structured")
                if isinstance(structured, dict):
                    structured = {k: v for k, v in structured.items()
                                  if k not in _EXCLUDED_STRUCTURED_KEYS}

                product = Product(
                    product_id=product_id,
                    vectordb_id=None,
                    product_name=data.get("상품명", ""),
                    brand=data.get("브랜드"),
                    category=category,
                    tag=tag,
                    sub_tag=sub_tag,
                    rating=_safe_float(data.get("별점")),
                    review_count=_safe_int(data.get("리뷰_갯수")) or 0,
                    original_price=_safe_int(data.get("원가")),
                    discount_rate=_safe_int(data.get("할인율")),
                    sale_price=_safe_int(data.get("판매가")),
                    skin_type=persona_tags.get("피부타입") or [],
                    concerns=persona_tags.get("고민키워드") or [],
                    preferred_colors=persona_tags.get("선호포인트색상") or [],
                    preferred_ingredients=persona_tags.get("선호성분") or [],
                    avoided_ingredients=persona_tags.get("기피성분") or [],
                    preferred_scents=persona_tags.get("선호향") or [],
                    lifestyle_values=persona_tags.get("가치관") or [],
                    exclusive_product=(
                        ", ".join(persona_tags["전용제품"])
                        if persona_tags.get("전용제품") else None
                    ),
                    personal_color=data.get("퍼스널컬러") or [],
                    skin_shades=data.get("피부호수") or persona_tags.get("피부톤번호") or [],
                    product_image_url=data.get("상품이미지") or [],
                    product_page_url=page_url,
                    product_comment=data.get("한줄소개"),
                    product_details=structured,
                )

                db.add(product)
                success += 1

                if idx % 100 == 0:
                    db.commit()
                    print(f"[seed] Progress: {idx}/{len(records)}")

            except IntegrityError:
                db.rollback()
                skip += 1
            except Exception as e:
                db.rollback()
                error += 1
                print(f"[seed] ERROR idx={idx} type={type(e).__name__}: {e}")

        db.commit()

    print(f"[seed] Done — success={success}, skipped={skip}, errors={error}")
    if error > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
