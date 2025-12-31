"""
JSONL 크롤링 데이터를 SQL INSERT 문으로 변환
data/product_data_for_db.jsonl 기준으로 수정
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = Path(__file__).parent / "init"


def escape_sql_string(s: str) -> str:
    """SQL 문자열 이스케이프"""
    if s is None or s == '':
        return 'NULL'
    return "'" + str(s).replace("'", "''").replace("\\", "\\\\") + "'"


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


def integer_array_to_sql(arr: List) -> str:
    """Python 리스트를 PostgreSQL INTEGER ARRAY로 변환"""
    if not arr:
        return "ARRAY[]::INTEGER[]"
    # 정수로 변환 가능한 것만 처리
    integers = []
    for item in arr:
        if item is None:
            continue
        try:
            integers.append(str(int(item)))
        except (ValueError, TypeError):
            continue
    if not integers:
        return "ARRAY[]::INTEGER[]"
    return f"ARRAY[{','.join(integers)}]::INTEGER[]"


def parse_number(value, default=0) -> str:
    """숫자 파싱 (정수)"""
    if value is None or value == '':
        return 'NULL'
    try:
        if isinstance(value, (int, float)):
            return str(int(value))
        # 문자열에서 숫자만 추출
        import re
        numbers = re.findall(r'\d+', str(value))
        if numbers:
            return str(int(''.join(numbers)))
        return 'NULL'
    except:
        return 'NULL'


def parse_rating(rating_value) -> str:
    """별점 파싱 (NUMERIC)"""
    if rating_value is None or rating_value == '':
        return 'NULL'
    try:
        if isinstance(rating_value, (int, float)):
            return str(float(rating_value))
        # 문자열에서 숫자 추출
        import re
        match = re.search(r'(\d+\.?\d*)', str(rating_value))
        if match:
            return str(float(match.group(1)))
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


def generate_product_sql(products_data: List[Dict[str, Any]], batch_size: int = 100) -> str:
    """상품 SQL 생성 (data JSONL 기준)"""
    sql_lines = [
        "-- ============================================================",
        "-- Products Data Migration",
        "-- Source: data/product_data_for_db.jsonl",
        "-- ============================================================\n"
    ]

    values_lines = []

    for idx, product_data in enumerate(products_data, 1):
        # product_id (JSONL에 이미 있음)
        product_id = product_data.get('product_id', '')
        if not product_id:
            print(f"[WARN] Line {idx}: product_id 없음, 스킵")
            continue

        # vectordb_id (JSONL에서 읽어오기)
        vectordb_id_value = product_data.get('vectordb_id', '')
        if vectordb_id_value:
            vectordb_id = escape_sql_string(vectordb_id_value)
        else:
            vectordb_id = 'NULL'

        # product_name
        product_name = product_data.get('상품명', '').strip()
        if not product_name:
            print(f"[WARN] Line {idx}: 상품명 없음, 스킵")
            continue

        # brand
        brand = escape_sql_string(product_data.get('브랜드', '').strip())

        # product_tag (태그)
        product_tag = escape_sql_string(product_data.get('태그', ''))

        # rating, review_count
        rating = parse_rating(product_data.get('별점'))
        review_count = parse_number(product_data.get('리뷰_갯수', 0))

        # 가격 정보
        original_price = parse_number(product_data.get('원가'))
        discount_rate = parse_number(product_data.get('할인율'))
        sale_price = parse_number(product_data.get('판매가'))

        # 페르소나 태그 추출
        persona_tags = product_data.get('페르소나태그', {})
        if not isinstance(persona_tags, dict):
            persona_tags = {}

        # skin_type (피부타입)
        skin_types = persona_tags.get('피부타입', [])
        if not isinstance(skin_types, list):
            skin_types = []
        skin_type_sql = array_to_sql(skin_types)

        # skin_concerns (고민키워드)
        concerns = persona_tags.get('고민키워드', [])
        if not isinstance(concerns, list):
            concerns = []
        skin_concerns_sql = array_to_sql(concerns)

        # preferred_colors (선호포인트색상)
        colors = persona_tags.get('선호포인트색상', [])
        if not isinstance(colors, list):
            colors = []
        preferred_colors_sql = array_to_sql(colors)

        # preferred_ingredients (선호성분)
        ingredients = persona_tags.get('선호성분', [])
        if not isinstance(ingredients, list):
            ingredients = []
        preferred_ingredients_sql = array_to_sql(ingredients)

        # avoided_ingredients (기피성분)
        avoided = persona_tags.get('기피성분', [])
        if not isinstance(avoided, list):
            avoided = []
        avoided_ingredients_sql = array_to_sql(avoided)

        # preferred_scents (선호향)
        scents = persona_tags.get('선호향', [])
        if not isinstance(scents, list):
            scents = []
        preferred_scents_sql = array_to_sql(scents)

        # values (가치관)
        values_list = persona_tags.get('가치관', [])
        if not isinstance(values_list, list):
            values_list = []
        values_sql = array_to_sql(values_list)

        # exclusive_product (전용제품)
        dedicated = persona_tags.get('전용제품', [])
        if isinstance(dedicated, list) and dedicated:
            exclusive_product = escape_sql_string(', '.join(str(x) for x in dedicated if x))
        elif isinstance(dedicated, str) and dedicated:
            exclusive_product = escape_sql_string(dedicated)
        else:
            exclusive_product = 'NULL'

        # personal_color (퍼스널컬러) - JSONL에는 없을 수 있음
        personal_colors = persona_tags.get('퍼스널컬러', [])
        if not isinstance(personal_colors, list):
            personal_colors = []
        personal_color_sql = array_to_sql(personal_colors)

        # skin_shades (피부톤번호) - INTEGER[] - JSONL에는 없을 수 있음
        skin_shades = persona_tags.get('피부톤번호', [])
        if not isinstance(skin_shades, list):
            skin_shades = []
        skin_shades_sql = integer_array_to_sql(skin_shades)

        # product_image_url (상품이미지)
        images = product_data.get('상품이미지', [])
        if not isinstance(images, list):
            images = []
        product_image_url_sql = array_to_sql(images)

        # product_page_url
        product_url = product_data.get('product_url', '')
        product_page_url = escape_sql_string(product_url)

        value = f"""(
    {escape_sql_string(product_id)},
    {vectordb_id},
    {escape_sql_string(product_name)},
    {brand},
    {product_tag},
    {rating},
    {review_count},
    {original_price},
    {discount_rate},
    {sale_price},
    {skin_type_sql},
    {skin_concerns_sql},
    {preferred_colors_sql},
    {preferred_ingredients_sql},
    {avoided_ingredients_sql},
    {preferred_scents_sql},
    {values_sql},
    {exclusive_product},
    {personal_color_sql},
    {skin_shades_sql},
    {product_image_url_sql},
    {product_page_url}
)"""
        values_lines.append(value)

        # 배치 단위로 INSERT 문 생성
        if len(values_lines) >= batch_size or idx == len(products_data):
            sql = f"""
INSERT INTO products (
    product_id, vectordb_id, product_name, brand, product_tag,
    rating, review_count, original_price, discount_rate, sale_price,
    skin_type, skin_concerns, preferred_colors,
    preferred_ingredients, avoided_ingredients, preferred_scents,
    values, exclusive_product, personal_color, skin_shades,
    product_image_url, product_page_url
)
VALUES
{','.join(values_lines)}
ON CONFLICT (product_id) DO NOTHING;
"""
            sql_lines.append(sql.strip())
            sql_lines.append("")
            values_lines = []

    return "\n\n".join(sql_lines)


def main():
    """메인 함수"""
    print("=" * 60)
    print("JSONL to SQL Converter")
    print("Source: data/product_data_for_db.jsonl")
    print("=" * 60)

    # 데이터 파일
    product_file = DATA_DIR / "product_data_for_db.jsonl"

    if not product_file.exists():
        print(f"[ERROR] File not found: {product_file}")
        return

    print(f"[INFO] Loading data from: {product_file.name}")
    products_data = load_jsonl(product_file)
    print(f"[INFO] Loaded {len(products_data)} products")

    # SQL 생성
    print("\n[INFO] Generating SQL...")

    # 상품 SQL
    product_sql = generate_product_sql(products_data)
    output_file = OUTPUT_DIR / "02-insert-products.sql"
    output_file.write_text(product_sql, encoding='utf-8')
    print(f"[OK] Created: {output_file}")

    print("\n" + "=" * 60)
    print("[OK] SQL file generated successfully!")
    print("=" * 60)

    print("\nHow to import:")
    print("  docker exec -i <container-name> psql -U postgres <db-name> < database/init/02-insert-products.sql")


if __name__ == "__main__":
    main()
