"""
JSONL 크롤링 데이터를 SQL INSERT 문으로 변환 (2512252207.jsonl 전용)
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent / "AI-INNOVATION-CHALLENGE-2026"
DATA_DIR = PROJECT_ROOT / "data" / "crawling_result"
OUTPUT_DIR = Path(__file__).parent / "init"


def escape_sql_string(s: str) -> str:
    """SQL 문자열 이스케이프"""
    if s is None or s == '':
        return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"


def json_to_sql_jsonb(obj: Any) -> str:
    """Python 객체를 PostgreSQL JSONB 문자열로 변환"""
    if obj is None or (isinstance(obj, dict) and not obj):
        return "'{}'"
    if isinstance(obj, list) and not obj:
        return "'[]'"
    json_str = json.dumps(obj, ensure_ascii=False)
    return "'" + json_str.replace("'", "''") + "'"


def array_to_sql(arr: List[str]) -> str:
    """Python 리스트를 PostgreSQL ARRAY로 변환"""
    if not arr:
        return "ARRAY[]::TEXT[]"
    # 배열 원소도 문자열로 처리
    escaped = []
    for item in arr:
        if item is None:
            continue
        item_str = str(item).strip()
        if item_str:
            escaped.append(escape_sql_string(item_str))
    if not escaped:
        return "ARRAY[]::TEXT[]"
    return f"ARRAY[{','.join(escaped)}]::TEXT[]"


def parse_price(price_value) -> str:
    """가격 파싱"""
    if price_value is None or price_value == '':
        return 'NULL'
    try:
        if isinstance(price_value, (int, float)):
            return str(float(price_value))
        # 문자열에서 숫자만 추출
        import re
        numbers = re.findall(r'\d+', str(price_value))
        if numbers:
            return str(float(''.join(numbers)))
        return 'NULL'
    except:
        return 'NULL'


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """JSONL 파일 로드"""
    data = []
    if not file_path.exists():
        print(f"[WARN] File not found: {file_path}")
        return data

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Line {line_num}: {e}")
                    continue
    return data


def generate_brand_sql(brands: Dict[str, int]) -> str:
    """브랜드 SQL 생성"""
    sql_lines = [
        "-- ============================================================",
        "-- Brands Data Migration (from 2512252207.jsonl)",
        "-- ============================================================\n"
    ]

    for brand_name in sorted(brands.keys()):
        sql = f"""INSERT INTO brands (name)
VALUES ({escape_sql_string(brand_name)})
ON CONFLICT (name) DO NOTHING;"""
        sql_lines.append(sql)

    return "\n\n".join(sql_lines)


def generate_product_sql(products_data: List[Dict[str, Any]], batch_size: int = 50) -> str:
    """상품 SQL 생성 (새 테이블 구조 반영)"""
    sql_lines = [
        "-- ============================================================",
        "-- Products Data Migration (from 2512252207.jsonl)",
        "-- ============================================================\n"
    ]

    # 브랜드별로 그룹화
    products_by_brand = {}
    for product in products_data:
        brand_name = product.get('브랜드', '').strip()
        if not brand_name:
            continue
        if brand_name not in products_by_brand:
            products_by_brand[brand_name] = []
        products_by_brand[brand_name].append(product)

    # 브랜드별로 SQL 생성
    for brand_name, brand_products in products_by_brand.items():
        sql_lines.append(f"-- Brand: {brand_name}")
        sql_lines.append(f"-- Products: {len(brand_products)}\n")

        # 배치 단위로 처리
        for i in range(0, len(brand_products), batch_size):
            batch = brand_products[i:i + batch_size]
            values_lines = []

            for product_data in batch:
                product_name = product_data.get('상품명', '').strip()
                if not product_name:
                    continue

                # 상품 코드 생성 (URL에서 추출 또는 해시)
                product_url = product_data.get('url', '')
                if 'onlineProdSn=' in product_url:
                    product_code = product_url.split('onlineProdSn=')[-1].split('&')[0]
                else:
                    product_code = hashlib.md5(product_name.encode('utf-8')).hexdigest()[:16]

                # 가격 정보
                original_price = parse_price(product_data.get('원가'))
                discount_rate = parse_price(product_data.get('할인율'))
                sale_price = parse_price(product_data.get('판매가'))

                # 평점/리뷰
                rating = parse_price(product_data.get('별점'))
                review_count = product_data.get('리뷰_갯수', 0)
                if review_count is None:
                    review_count = 0

                # 이미지 URL
                image_urls = product_data.get('상품이미지', [])
                if isinstance(image_urls, str):
                    image_urls = [image_urls]
                image_urls_sql = array_to_sql(image_urls) if image_urls else "ARRAY[]::TEXT[]"

                # 페르소나 태그 추출
                persona_tags = product_data.get('페르소나태그', {})
                if not isinstance(persona_tags, dict):
                    persona_tags = {}

                skin_types = persona_tags.get('피부타입', [])
                if isinstance(skin_types, str):
                    skin_types = [skin_types]

                concern_keywords = persona_tags.get('고민키워드', [])
                if isinstance(concern_keywords, str):
                    concern_keywords = [concern_keywords]

                makeup_colors = persona_tags.get('선호포인트색상', [])
                if isinstance(makeup_colors, str):
                    makeup_colors = [makeup_colors]

                preferred_ingredients = persona_tags.get('선호성분', [])
                if isinstance(preferred_ingredients, str):
                    preferred_ingredients = [preferred_ingredients]

                avoided_ingredients = persona_tags.get('기피성분', [])
                if isinstance(avoided_ingredients, str):
                    avoided_ingredients = [avoided_ingredients]

                preferred_scents = persona_tags.get('선호향', [])
                if isinstance(preferred_scents, str):
                    preferred_scents = [preferred_scents]

                values_keywords = persona_tags.get('가치관', [])
                if isinstance(values_keywords, str):
                    values_keywords = [values_keywords]

                dedicated_products = persona_tags.get('전용제품', [])
                if isinstance(dedicated_products, str):
                    dedicated_products = [dedicated_products]

                # GPT 생성 문서
                generated_doc = product_data.get('document', '')

                # tag 정보
                tags = product_data.get('tag', {})
                if isinstance(tags, str):
                    tags = {'raw': tags}

                # 구매자 통계
                buyer_stats = product_data.get('구매자_통계', {})
                if isinstance(buyer_stats, str):
                    buyer_stats = {'raw': buyer_stats}

                value = f"""(
    (SELECT id FROM brands WHERE name = {escape_sql_string(brand_name)} LIMIT 1),
    NULL,
    NULL,
    {escape_sql_string(product_code)},
    {escape_sql_string(product_name)},
    NULL,
    NULL,
    {original_price},
    {discount_rate},
    {sale_price},
    {rating},
    {review_count},
    {array_to_sql(skin_types)},
    ARRAY[]::TEXT[],
    ARRAY[]::TEXT[],
    {array_to_sql(concern_keywords)},
    {array_to_sql(makeup_colors)},
    {array_to_sql(preferred_ingredients)},
    {array_to_sql(avoided_ingredients)},
    {array_to_sql(preferred_scents)},
    {array_to_sql(values_keywords)},
    {array_to_sql(dedicated_products)},
    {escape_sql_string(product_url)},
    {image_urls_sql},
    NULL,
    {escape_sql_string(generated_doc)},
    {json_to_sql_jsonb(tags)},
    {json_to_sql_jsonb(buyer_stats)},
    '{{}}',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)"""
                values_lines.append(value)

            if not values_lines:
                continue

            # SQL INSERT 문 생성
            sql = f"""
INSERT INTO products (
    brand_id, vector_db_id, indexing_number,
    product_code, product_name, category, sub_category,
    original_price, discount_rate, sale_price,
    rating, review_count,
    skin_types, personal_colors, base_shades,
    concern_keywords, makeup_colors,
    preferred_ingredients, avoided_ingredients, preferred_scents,
    values_keywords, dedicated_products,
    product_url, image_urls,
    description, generated_document,
    tags, buyer_statistics, detailed_info,
    created_at, updated_at
)
VALUES
{','.join(values_lines)}
ON CONFLICT (brand_id, product_code) DO NOTHING;
"""
            sql_lines.append(sql.strip())
            sql_lines.append("")

    return "\n\n".join(sql_lines)


def main():
    """메인 함수"""
    print("=" * 60)
    print("JSONL to SQL Converter (2512252207.jsonl)")
    print("=" * 60)

    # 데이터 파일
    product_file = DATA_DIR / "2512252207.jsonl"

    if not product_file.exists():
        print(f"[ERROR] File not found: {product_file}")
        return

    print(f"[INFO] Loading data from: {product_file.name}")
    products_data = load_jsonl(product_file)
    print(f"[INFO] Loaded {len(products_data)} products")

    # 브랜드 추출
    brands = {}
    for product in products_data:
        brand_name = product.get('브랜드', '').strip()
        if brand_name and brand_name not in brands:
            brands[brand_name] = len(brands) + 1

    print(f"[INFO] Found {len(brands)} unique brands")

    # SQL 생성
    print("\n[INFO] Generating SQL...")

    # 브랜드 SQL
    brand_sql = generate_brand_sql(brands)
    brand_file = OUTPUT_DIR / "04-insert-brands.sql"
    brand_file.write_text(brand_sql, encoding='utf-8')
    print(f"[OK] Created: {brand_file}")

    # 상품 SQL
    product_sql = generate_product_sql(products_data)
    product_file = OUTPUT_DIR / "05-insert-products.sql"
    product_file.write_text(product_sql, encoding='utf-8')
    print(f"[OK] Created: {product_file}")

    print("\n" + "=" * 60)
    print("[OK] SQL files generated successfully!")
    print("=" * 60)

    print("\nHow to import:")
    print("  1. docker exec -i ai-innovation-postgres psql -U postgres ai_innovation_db < init/04-insert-brands.sql")
    print("  2. docker exec -i ai-innovation-postgres psql -U postgres ai_innovation_db < init/05-insert-products.sql")


if __name__ == "__main__":
    main()
