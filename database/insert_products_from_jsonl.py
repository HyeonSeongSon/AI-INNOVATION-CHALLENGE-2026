"""
JSONL 파일에서 직접 PostgreSQL에 상품 데이터 삽입
"""

import json
from pathlib import Path
from database import get_db
from models import Product
from sqlalchemy.exc import IntegrityError

def insert_products_from_jsonl():
    """JSONL 파일에서 상품 데이터를 읽어서 DB에 삽입"""

    # 파일 경로
    jsonl_file = Path(__file__).parent.parent / "data" / "product_data_for_db.jsonl"

    if not jsonl_file.exists():
        print("=" * 80)
        print("❌ 오류: 상품 데이터 파일을 찾을 수 없습니다!")
        print("=" * 80)
        print(f"필요한 파일: {jsonl_file}")
        print()
        print("⚠️  이 파일은 데이터베이스 설정에 필수입니다.")
        print()
        print("📋 다음 단계를 먼저 완료해주세요:")
        print()
        print("1. 벡터 데이터베이스에 상품 데이터 색인")
        print("   → 벡터 인덱싱 스크립트를 실행하여 임베딩 생성")
        print("   → 이 과정에서 'product_data_for_db.jsonl' 파일이 생성됩니다")
        print()
        print("2. 파일이 다음 위치에 있는지 확인:")
        print(f"   {jsonl_file}")
        print()
        print("3. 이 스크립트를 다시 실행")
        print("=" * 80)
        return

    print("=" * 60)
    print("JSONL to PostgreSQL Direct Insert")
    print("=" * 60)
    print(f"Source: {jsonl_file}")
    print()

    # JSONL 파일 읽기
    products_data = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                products_data.append(json.loads(line))

    print(f"Loaded {len(products_data)} products from JSONL")
    print()

    # 데이터베이스에 삽입
    success_count = 0
    skip_count = 0
    error_count = 0

    with next(get_db()) as db:
        for idx, data in enumerate(products_data, 1):
            try:
                # 페르소나 태그 추출
                persona_tags = data.get('페르소나태그', {})
                if not isinstance(persona_tags, dict):
                    persona_tags = {}

                # Product 객체 생성
                product = Product(
                    product_id=data.get('product_id'),
                    vectordb_id=data.get('vectordb_id'),
                    product_name=data.get('상품명', ''),
                    brand=data.get('브랜드'),
                    product_tag=data.get('태그'),
                    rating=data.get('별점'),
                    review_count=data.get('리뷰_갯수', 0),
                    original_price=data.get('원가'),
                    discount_rate=data.get('할인율'),
                    sale_price=data.get('판매가'),
                    skin_type=persona_tags.get('피부타입', []),
                    skin_concerns=persona_tags.get('고민키워드', []),
                    preferred_colors=persona_tags.get('선호포인트색상', []),
                    preferred_ingredients=persona_tags.get('선호성분', []),
                    avoided_ingredients=persona_tags.get('기피성분', []),
                    preferred_scents=persona_tags.get('선호향', []),
                    values=persona_tags.get('가치관', []),
                    exclusive_product=', '.join(persona_tags.get('전용제품', [])) if persona_tags.get('전용제품') else None,
                    personal_color=persona_tags.get('퍼스널컬러', []),
                    skin_shades=persona_tags.get('피부톤번호', []),
                    product_image_url=data.get('상품이미지', []),
                    product_page_url=data.get('product_url')
                )

                db.add(product)
                success_count += 1

                # 100개마다 커밋
                if idx % 100 == 0:
                    db.commit()
                    print(f"Progress: {idx}/{len(products_data)} products inserted")

            except IntegrityError:
                db.rollback()
                skip_count += 1
            except Exception as e:
                db.rollback()
                error_count += 1
                print(f"[ERROR] Line {idx}: {e}")

        # 마지막 커밋
        db.commit()

    print()
    print("=" * 60)
    print("Insert Complete!")
    print("=" * 60)
    print(f"Success: {success_count}")
    print(f"Skipped (duplicate): {skip_count}")
    print(f"Errors: {error_count}")
    print(f"Total: {len(products_data)}")
    print("=" * 60)


if __name__ == "__main__":
    insert_products_from_jsonl()