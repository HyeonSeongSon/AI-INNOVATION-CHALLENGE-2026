#!/usr/bin/env python3
"""
페르소나 태그를 메인 데이터 파일에 병합하는 스크립트
상품명을 기준으로 매칭하여 페르소나태그 필드를 추가합니다.
"""

import json
from pathlib import Path
from typing import Dict


def load_persona_tags(persona_file: Path) -> Dict[str, Dict]:
    """
    페르소나 태그 파일에서 상품명을 키로 하는 딕셔너리 생성

    Args:
        persona_file: 페르소나 태그가 포함된 JSONL 파일 경로

    Returns:
        {상품명: 페르소나태그} 형태의 딕셔너리
    """
    persona_map = {}

    print(f"페르소나 태그 파일 로드: {persona_file}")

    with open(persona_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                record = json.loads(line.strip())
                product_name = record.get('상품명', '')
                persona_tag = record.get('페르소나태그')

                if product_name and persona_tag:
                    persona_map[product_name] = persona_tag

            except json.JSONDecodeError as e:
                print(f"[경고] 페르소나 파일 {line_num}번째 줄 JSON 파싱 실패: {e}")
                continue

    print(f"총 {len(persona_map)}개의 페르소나 태그 로드 완료\n")
    return persona_map


def merge_persona_tags(
    source_file: Path,
    persona_map: Dict[str, Dict],
    output_file: Path
) -> None:
    """
    원본 파일에 페르소나 태그를 병합하여 새 파일로 저장

    Args:
        source_file: 원본 JSONL 파일 경로
        persona_map: 상품명을 키로 하는 페르소나 태그 딕셔너리
        output_file: 출력 JSONL 파일 경로
    """
    print(f"원본 파일: {source_file}")
    print(f"출력 파일: {output_file}")

    processed_count = 0
    tagged_count = 0
    no_tag_count = 0

    with open(source_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                record = json.loads(line.strip())
                product_name = record.get('상품명', '')

                # 상품명으로 페르소나 태그 찾기
                if product_name in persona_map:
                    record['페르소나태그'] = persona_map[product_name]
                    tagged_count += 1
                else:
                    no_tag_count += 1

                # 결과 저장
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"[경고] 원본 파일 {line_num}번째 줄 JSON 파싱 실패: {e}")
                continue

    print(f"\n완료!")
    print(f"총 처리된 레코드: {processed_count}개")
    print(f"페르소나태그 추가된 레코드: {tagged_count}개")
    print(f"페르소나태그 없는 레코드: {no_tag_count}개")
    if processed_count > 0:
        print(f"태그 추가 비율: {tagged_count/processed_count*100:.1f}%")


if __name__ == "__main__":
    # 파일 경로 설정
    BASE_DIR = Path(__file__).parent

    # 입력 파일
    source_file = BASE_DIR / "product_data_251225a.jsonl"
    persona_file = BASE_DIR / "product_data_251225a_with_persona_tags.jsonl"

    # 출력 파일
    output_file = BASE_DIR / "2512252207.jsonl"

    # 파일 존재 확인
    if not source_file.exists():
        print(f"오류: 원본 파일이 존재하지 않습니다: {source_file}")
        exit(1)

    if not persona_file.exists():
        print(f"오류: 페르소나 태그 파일이 존재하지 않습니다: {persona_file}")
        exit(1)

    # 페르소나 태그 로드
    persona_map = load_persona_tags(persona_file)

    # 페르소나 태그 병합
    merge_persona_tags(source_file, persona_map, output_file)
