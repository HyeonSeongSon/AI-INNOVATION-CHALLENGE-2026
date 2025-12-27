"""
document 필드가 없는 레코드만 추출하는 스크립트

사용법:
    python extract_no_document.py
"""

import json
from pathlib import Path


def extract_no_document_records(input_file: Path, output_file: Path) -> None:
    """
    document 필드가 없는 레코드만 추출하여 새 파일로 저장

    Args:
        input_file: 입력 JSONL 파일 경로
        output_file: 출력 JSONL 파일 경로
    """
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")
    print("-" * 80)

    if not input_file.exists():
        print(f"에러: 입력 파일이 존재하지 않습니다: {input_file}")
        return

    # 출력 파일 디렉토리 생성
    output_file.parent.mkdir(parents=True, exist_ok=True)

    total_count = 0
    no_document_count = 0
    has_document_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                line = line.strip()
                if not line:  # 빈 줄 건너뛰기
                    continue

                record = json.loads(line)
                total_count += 1

                # document 필드가 없는 경우만 저장
                if 'document' not in record:
                    outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                    no_document_count += 1

                    # 처음 3개만 출력
                    if no_document_count <= 3:
                        product_name = record.get('상품명', 'N/A')
                        print(f"[{line_num}] document 없음: {product_name[:50]}...")
                else:
                    has_document_count += 1

            except json.JSONDecodeError as e:
                print(f"  경고: JSON 파싱 실패 (라인 {line_num}): {e}")
            except Exception as e:
                print(f"  에러: 처리 실패 (라인 {line_num}): {e}")

    print("\n" + "=" * 80)
    print(f"추출 완료!")
    print(f"  - 전체 레코드: {total_count}")
    print(f"  - document 없음: {no_document_count}")
    print(f"  - document 있음: {has_document_count}")
    print(f"  - 출력 파일: {output_file}")
    print("=" * 80)


def main():
    """메인 함수"""
    # 파일 경로 설정
    project_root = Path(__file__).parent.parent.parent

    # 입력 파일
    input_file = project_root / "data" / "crawling_result" / "product_crawling_251225_dtt.jsonl"

    # 출력 파일 (원본 파일명 + _no_doc)
    output_file = project_root / "data" / "crawling_result" / "product_crawling_251225_no_doc.jsonl"

    # 추출 실행
    extract_no_document_records(input_file, output_file)


if __name__ == "__main__":
    main()
