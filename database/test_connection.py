"""
Database Connection Test Script
데이터베이스 연결 및 기본 쿼리 테스트
"""

from database import get_db, check_connection
from models import Brand, Product, Persona, ProductPersona


def test_connection():
    """데이터베이스 연결 테스트"""
    print("\n" + "=" * 60)
    print("1. Database Connection Test")
    print("=" * 60)

    if check_connection():
        print("[OK] Connection successful!")
        return True
    else:
        print("[ERROR] Connection failed!")
        return False


def test_tables():
    """테이블 존재 확인"""
    print("\n" + "=" * 60)
    print("2. Table Check")
    print("=" * 60)

    db = next(get_db())

    tables = [
        ("brands", Brand),
        ("products", Product),
        ("personas", Persona),
        ("product_personas", ProductPersona)
    ]

    for table_name, model in tables:
        try:
            count = db.query(model).count()
            print(f"[OK] {table_name}: {count} records")
        except Exception as e:
            print(f"[ERROR] {table_name}: {e}")


def test_queries():
    """기본 쿼리 테스트"""
    print("\n" + "=" * 60)
    print("3. Basic Query Test")
    print("=" * 60)

    db = next(get_db())

    # 브랜드 조회
    print("\n[Brands]")
    brands = db.query(Brand).limit(5).all()
    for brand in brands:
        print(f"  - {brand.name}")

    # 페르소나 조회
    print("\n[Personas]")
    personas = db.query(Persona).all()
    for persona in personas:
        print(f"  - {persona.name} ({persona.persona_key})")

    # 상품 조회
    print("\n[Products (max 5)]")
    products = db.query(Product).limit(5).all()
    for product in products:
        print(f"  - {product.product_name} ({product.category})")


def test_relationships():
    """관계 테스트"""
    print("\n" + "=" * 60)
    print("4. Relationship Test")
    print("=" * 60)

    db = next(get_db())

    # 브랜드-상품 관계
    print("\n[Products per Brand]")
    brands = db.query(Brand).limit(3).all()
    for brand in brands:
        product_count = len(brand.products)
        print(f"  - {brand.name}: {product_count} products")

    # 페르소나-상품 매핑
    print("\n[Product Mappings per Persona]")
    personas = db.query(Persona).all()
    for persona in personas:
        mapping_count = len(persona.product_personas)
        print(f"  - {persona.name}: {mapping_count} mappings")


def main():
    """메인 테스트 함수"""
    print("\n" + "=" * 60)
    print("PostgreSQL Database Test Suite")
    print("=" * 60)

    try:
        # 1. 연결 테스트
        if not test_connection():
            return

        # 2. 테이블 확인
        test_tables()

        # 3. 기본 쿼리 테스트
        test_queries()

        # 4. 관계 테스트
        test_relationships()

        print("\n" + "=" * 60)
        print("[OK] All tests completed!")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[ERROR] Test failed: {e}")
        print("=" * 60)


if __name__ == "__main__":
    main()
