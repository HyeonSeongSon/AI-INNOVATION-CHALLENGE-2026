"""
데이터베이스 초기화 및 데이터 색인 파이프라인
테이블 생성 → 데이터 삽입 → 검증
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy import text

# database/ 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import (
    engine,
    get_db,
    init_db,
    drop_all_tables,
    check_connection,
    db_config
)
from core.models import Product, Persona


class DatabaseSetupPipeline:
    """데이터베이스 초기화 파이프라인"""

    def __init__(self, reset: bool = False):
        """
        Args:
            reset: True인 경우 기존 테이블 삭제 후 재생성
        """
        self.reset = reset
        self.data_dir = Path(__file__).parent.parent / "data"
        self.product_jsonl = self.data_dir / "product_data_for_db.jsonl"

    def run(self):
        """전체 파이프라인 실행"""
        print("=" * 80)
        print("DATABASE SETUP PIPELINE")
        print("=" * 80)
        print(f"Database: {db_config.database}")
        print(f"Host: {db_config.host}:{db_config.port}")
        print(f"Reset mode: {self.reset}")
        print("=" * 80)
        print()

        # 1. 데이터베이스 연결 확인
        if not self.step_1_check_connection():
            return False

        # 2. 테이블 생성/재생성
        if not self.step_2_create_tables():
            return False

        # 3. 상품 데이터 삽입
        if not self.step_3_insert_products():
            return False

        # 4. 검증
        if not self.step_4_validate():
            return False

        print()
        print("=" * 80)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        return True

    def step_1_check_connection(self) -> bool:
        """Step 1: 데이터베이스 연결 확인"""
        print("\n[STEP 1] Checking database connection...")
        print("-" * 80)

        if not check_connection():
            print("❌ Database connection failed!")
            print("\nPlease check:")
            print("  1. PostgreSQL server is running")
            print("  2. .env file has correct database credentials")
            print("  3. Database exists (or create it first)")
            return False

        print("✅ Connection successful")
        return True

    def step_2_create_tables(self) -> bool:
        """Step 2: 테이블 생성 (reset=True인 경우 기존 테이블 삭제)"""
        print("\n[STEP 2] Creating database tables...")
        print("-" * 80)

        try:
            if self.reset:
                print("⚠️  Dropping existing tables...")
                drop_all_tables()

            print("Creating tables...")
            init_db()

            # 생성된 테이블 확인
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result]

            print(f"\nCreated tables ({len(tables)}):")
            for table in tables:
                print(f"  - {table}")

            print("✅ Tables created successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to create tables: {e}")
            return False

    def step_3_insert_products(self) -> bool:
        """Step 3: 상품 데이터 삽입"""
        print("\n[STEP 3] Inserting product data...")
        print("-" * 80)

        if not self.product_jsonl.exists():
            print()
            print("=" * 80)
            print("❌ 오류: 상품 데이터 파일을 찾을 수 없습니다!")
            print("=" * 80)
            print(f"필요한 파일: {self.product_jsonl}")
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
            print(f"   {self.product_jsonl}")
            print()
            print("3. 이 스크립트를 다시 실행:")
            print("   python setup_pipeline.py")
            print("=" * 80)
            print()
            return False

        try:
            # JSONL 파일 읽기
            products_data = []
            with open(self.product_jsonl, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        products_data.append(json.loads(line))

            print(f"Loaded {len(products_data)} products from JSONL")

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
                            product_page_url=data.get('product_url'),
                            product_comment=data.get('한줄소개')
                        )

                        db.add(product)
                        success_count += 1

                        # 100개마다 커밋
                        if idx % 100 == 0:
                            db.commit()
                            print(f"  Progress: {idx}/{len(products_data)} products inserted")

                    except Exception as e:
                        db.rollback()
                        error_count += 1
                        if error_count <= 5:  # 처음 5개 에러만 출력
                            print(f"  [ERROR] Product {idx}: {e}")

                # 마지막 커밋
                db.commit()

            print()
            print(f"Insert summary:")
            print(f"  - Success: {success_count}")
            print(f"  - Errors: {error_count}")
            print(f"  - Total: {len(products_data)}")

            if error_count > 0:
                print(f"⚠️  {error_count} products failed to insert")

            print("✅ Product data inserted")
            return True

        except Exception as e:
            print(f"❌ Failed to insert products: {e}")
            return False

    def step_4_validate(self) -> bool:
        """Step 4: 데이터 검증"""
        print("\n[STEP 4] Validating data...")
        print("-" * 80)

        try:
            with next(get_db()) as db:
                # 상품 개수 확인
                product_count = db.query(Product).count()
                print(f"Total products in database: {product_count}")

                # 브랜드별 상품 개수
                brand_counts = db.execute(text("""
                    SELECT brand, COUNT(*) as count
                    FROM products
                    WHERE brand IS NOT NULL
                    GROUP BY brand
                    ORDER BY count DESC
                    LIMIT 10
                """)).fetchall()

                print(f"\nTop 10 brands by product count:")
                for brand, count in brand_counts:
                    print(f"  - {brand}: {count} products")

                # 샘플 상품 출력
                sample_products = db.query(Product).limit(3).all()
                print(f"\nSample products:")
                for p in sample_products:
                    print(f"  - [{p.product_id}] {p.product_name} ({p.brand})")

            print("✅ Validation completed")
            return True

        except Exception as e:
            print(f"❌ Validation failed: {e}")
            return False


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='Database Setup Pipeline')
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Drop existing tables and recreate (WARNING: deletes all data)'
    )

    args = parser.parse_args()

    if args.reset:
        print("WARNING: This will DELETE all existing data!")
        response = input("Are you sure? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    pipeline = DatabaseSetupPipeline(reset=args.reset)
    success = pipeline.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
