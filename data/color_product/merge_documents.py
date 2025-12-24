"""
두 JSONL 파일을 매칭하여 document와 tag 필드 추가

상품명과 URL이 일치하는 경우 '생성된_문서'와 '태그'를 'document'와 'tag'로 추가

사용법:
    python merge_documents.py
"""

import json
from pathlib import Path
from typing import Dict, Set


def load_source_data(source_file: Path) -> Dict[str, Dict]:
    """
    소스 파일(생성된_문서, 태그 포함)을 로드하여 딕셔너리로 반환

    Args:
        source_file: 소스 JSONL 파일 경로

    Returns:
        {상품명: {document: ..., tag: ...}} 형태의 딕셔너리
    """
    source_map = {}

    print(f"소스 파일 로드 중: {source_file}")

    with open(source_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                record = json.loads(line.strip())

                # 키 생성: 상품명만 사용
                product_name = record.get('상품명', '')

                if product_name:
                    # document와 tag 추출
                    doc_data = {}

                    if '생성된_문서' in record:
                        doc_data['document'] = record['생성된_문서']

                    if '태그' in record:
                        doc_data['tag'] = record['태그']

                    # 데이터가 있는 경우만 저장
                    if doc_data:
                        source_map[product_name] = doc_data

            except json.JSONDecodeError as e:
                print(f"  경고: 소스 파일 JSON 파싱 실패 (라인 {line_num}): {e}")
            except Exception as e:
                print(f"  경고: 소스 파일 처리 실패 (라인 {line_num}): {e}")

    print(f"  → {len(source_map)}개 항목 로드 완료\n")
    return source_map


def merge_files(
    target_file: Path,
    source_map: Dict[str, Dict],
    output_file: Path
) -> None:
    """
    타겟 파일에 소스 데이터를 매칭하여 병합

    Args:
        target_file: 대상 JSONL 파일 (컬러 정보 등이 있는 파일)
        source_map: 소스 데이터 맵
        output_file: 출력 JSONL 파일
    """
    print(f"타겟 파일: {target_file}")
    print(f"출력 파일: {output_file}")
    print("-" * 80)

    matched_count = 0
    unmatched_count = 0
    total_count = 0

    with open(target_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                record = json.loads(line.strip())
                total_count += 1

                # 키 생성: 상품명만 사용
                product_name = record.get('상품명', '')

                if product_name:
                    # 매칭되는 데이터가 있으면 추가
                    if product_name in source_map:
                        source_data = source_map[product_name]

                        # document 추가
                        if 'document' in source_data:
                            record['document'] = source_data['document']

                        # tag 추가
                        if 'tag' in source_data:
                            record['tag'] = source_data['tag']

                        matched_count += 1

                        if matched_count <= 3:  # 처음 3개만 출력
                            print(f"[{line_num}] 매칭 완료: {product_name[:30]}...")
                    else:
                        unmatched_count += 1

                # 결과 저장 (매칭 여부와 관계없이)
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')

            except json.JSONDecodeError as e:
                print(f"  경고: JSON 파싱 실패 (라인 {line_num}): {e}")
            except Exception as e:
                print(f"  에러: 처리 실패 (라인 {line_num}): {e}")

    print("\n" + "=" * 80)
    print(f"병합 완료!")
    print(f"  - 전체 레코드: {total_count}")
    print(f"  - 매칭 성공: {matched_count}")
    print(f"  - 매칭 실패: {unmatched_count}")
    print(f"  - 출력 파일: {output_file}")
    print("=" * 80)


def main():
    """메인 함수"""
    # 파일 경로 설정
    project_root = Path(__file__).parent.parent.parent

    # 소스 파일 (생성된_문서, 태그 포함)
    source_file = project_root / "data" / "product_document" / "product_documents_v3_tagged.jsonl"

    # 타겟 파일 (병합할 대상)
    target_file = project_root / "data" / "crawling_result" / "product_crawling_251225_dtt.jsonl"

    # 출력 파일 (원본 파일명 + dt)
    output_file = project_root / "data" / "crawling_result" / "product_crawling_251225_good.jsonl"

    # 파일 존재 확인
    if not source_file.exists():
        print(f"에러: 소스 파일이 존재하지 않습니다: {source_file}")
        return

    if not target_file.exists():
        print(f"에러: 타겟 파일이 존재하지 않습니다: {target_file}")
        return

    # 출력 디렉토리 생성
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 1단계: 소스 데이터 로드
    source_map = load_source_data(source_file)

    # 2단계: 파일 병합
    merge_files(target_file, source_map, output_file)


if __name__ == "__main__":
    main()
