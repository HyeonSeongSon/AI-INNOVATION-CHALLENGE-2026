#!/usr/bin/env python3
"""
tag 필드를 제외한 데이터 추출 스크립트
"""

import json
from pathlib import Path


def remove_tag_field(input_file: Path, output_file: Path) -> None:
    """
    JSONL 파일에서 tag 필드를 제거하고 새 파일로 저장

    Args:
        input_file: 입력 JSONL 파일 경로
        output_file: 출력 JSONL 파일 경로
    """
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")

    processed_count = 0
    removed_tag_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                # JSON 파싱
                record = json.loads(line.strip())

                # tag 필드가 있으면 제거
                if 'tag' in record:
                    del record['tag']
                    removed_tag_count += 1

                # 결과 저장
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"[경고] {line_num}번째 줄 JSON 파싱 실패: {e}")
                continue

    print(f"\n완료!")
    print(f"총 처리된 레코드: {processed_count}개")
    print(f"tag 필드 제거된 레코드: {removed_tag_count}개")


if __name__ == "__main__":
    # 파일 경로 설정
    BASE_DIR = Path(__file__).parent
    input_file = BASE_DIR / "product_crawling_251225_good.jsonl"
    output_file = BASE_DIR / "product_crawling_251225_no_tag.jsonl"

    # 입력 파일 존재 확인
    if not input_file.exists():
        print(f"오류: 입력 파일이 존재하지 않습니다: {input_file}")
        exit(1)

    # tag 필드 제거
    remove_tag_field(input_file, output_file)
