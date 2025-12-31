"""
JSONL 파일 병합 스크립트
product_data_251231.jsonl과 product_id_mapping.jsonl을 병합하여
vectordb_id를 product_id 다음에 추가
"""

import json
from collections import OrderedDict
from pathlib import Path


def merge_product_data():
    """
    product_data_251231.jsonl과 product_id_mapping.jsonl을 병합
    vectordb_id를 product_id 바로 다음에 추가
    """
    # 파일 경로 설정
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"

    mapping_file = data_dir / "product_id_mapping.jsonl"
    product_file = data_dir / "product_data_251231.jsonl"
    output_file = data_dir / "product_data_for_db.jsonl"

    print("=" * 60)
    print("JSONL 파일 병합 스크립트")
    print("=" * 60)
    print(f"매핑 파일: {mapping_file}")
    print(f"상품 파일: {product_file}")
    print(f"출력 파일: {output_file}")
    print("=" * 60)

    # 1. product_id_mapping 로드
    print("\n[1/3] product_id_mapping.jsonl 로드 중...")
    mapping = {}

    if not mapping_file.exists():
        print(f"❌ 오류: {mapping_file} 파일을 찾을 수 없습니다.")
        return

    with open(mapping_file, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            mapping[data['product_id']] = data['vector_db_id']

    print(f"✅ {len(mapping)}개의 매핑 로드 완료")

    # 2. product_data_251231 로드 및 병합
    print("\n[2/3] product_data_251231.jsonl 병합 중...")

    if not product_file.exists():
        print(f"❌ 오류: {product_file} 파일을 찾을 수 없습니다.")
        return

    merged_count = 0
    not_found_count = 0
    output_lines = []

    with open(product_file, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            product_id = data.get('product_id')

            # OrderedDict로 순서 유지
            ordered_data = OrderedDict()
            ordered_data['product_id'] = data['product_id']

            # vectordb_id 추가 (product_id 바로 다음에)
            if product_id in mapping:
                ordered_data['vectordb_id'] = mapping[product_id]
                merged_count += 1
            else:
                ordered_data['vectordb_id'] = None
                not_found_count += 1

            # 나머지 필드 추가
            for key, value in data.items():
                if key != 'product_id':
                    ordered_data[key] = value

            output_lines.append(json.dumps(ordered_data, ensure_ascii=False))

    print(f"✅ vectordb_id 매칭: {merged_count}개")
    if not_found_count > 0:
        print(f"⚠️  매칭 실패 (None 처리): {not_found_count}개")

    # 3. 결과 저장
    print(f"\n[3/3] {output_file} 저장 중...")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"✅ 저장 완료")

    # 결과 요약
    print("\n" + "=" * 60)
    print("병합 완료!")
    print("=" * 60)
    print(f"총 상품 수: {merged_count + not_found_count}")
    print(f"vectordb_id 매칭: {merged_count}개")
    print(f"매칭 실패: {not_found_count}개")
    print(f"출력 파일: {output_file}")
    print(f"파일 크기: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    merge_product_data()
