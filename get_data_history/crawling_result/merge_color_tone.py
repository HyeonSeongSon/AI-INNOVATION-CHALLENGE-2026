#!/usr/bin/env python3
"""
컬러/톤 정보를 메인 데이터 파일에 병합하는 스크립트
상품명을 기준으로 매칭하여 color_info와 tone_info 필드를 추가합니다.
"""

import json
from pathlib import Path
from typing import Dict, Optional


def load_color_tone_data(file1: Path, file2: Path) -> Dict[str, Dict]:
    """
    두 개의 컬러/톤 파일에서 상품명을 키로 하는 딕셔너리 생성

    Args:
        file1: 첫 번째 컬러/톤 파일
        file2: 두 번째 컬러/톤 파일

    Returns:
        {상품명: {color_info, tone_info}} 형태의 딕셔너리
    """
    data_map = {}

    # 첫 번째 파일 로드
    print(f"파일 1 로드: {file1}")
    if file1.exists():
        with open(file1, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    record = json.loads(line.strip())
                    product_name = record.get('상품명', '')

                    if product_name:
                        data_map[product_name] = {
                            'color_info': record.get('color_info'),
                            'tone_info': record.get('tone_info')
                        }

                except json.JSONDecodeError as e:
                    print(f"[경고] 파일1 {line_num}번째 줄 JSON 파싱 실패: {e}")
                    continue

        print(f"  -> {len(data_map)}개 로드 완료")
    else:
        print(f"  -> 파일이 존재하지 않습니다")

    # 두 번째 파일 로드 (덮어쓰기 또는 추가)
    print(f"\n파일 2 로드: {file2}")
    if file2.exists():
        count_before = len(data_map)
        with open(file2, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    record = json.loads(line.strip())
                    product_name = record.get('상품명', '')

                    if product_name:
                        # 이미 존재하는 경우 덮어쓰기, 없으면 새로 추가
                        data_map[product_name] = {
                            'color_info': record.get('color_info'),
                            'tone_info': record.get('tone_info')
                        }

                except json.JSONDecodeError as e:
                    print(f"[경고] 파일2 {line_num}번째 줄 JSON 파싱 실패: {e}")
                    continue

        count_after = len(data_map)
        print(f"  -> {count_after - count_before}개 추가, 총 {count_after}개")
    else:
        print(f"  -> 파일이 존재하지 않습니다")

    print(f"\n총 {len(data_map)}개의 컬러/톤 데이터 로드 완료\n")
    return data_map


def merge_color_tone_info(
    source_file: Path,
    color_tone_map: Dict[str, Dict],
    output_file: Path
) -> None:
    """
    원본 파일에 컬러/톤 정보를 병합하여 새 파일로 저장

    Args:
        source_file: 원본 JSONL 파일 경로
        color_tone_map: 상품명을 키로 하는 컬러/톤 딕셔너리
        output_file: 출력 JSONL 파일 경로
    """
    print(f"원본 파일: {source_file}")
    print(f"출력 파일: {output_file}")

    processed_count = 0
    color_added_count = 0
    tone_added_count = 0
    no_match_count = 0

    with open(source_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                record = json.loads(line.strip())
                product_name = record.get('상품명', '')

                # 상품명으로 컬러/톤 정보 찾기
                if product_name in color_tone_map:
                    color_tone_data = color_tone_map[product_name]

                    color_info = color_tone_data.get('color_info')
                    tone_info = color_tone_data.get('tone_info')

                    # color_info 추가 조건 확인
                    if color_info is not None:
                        # color_info가 비어있는지 확인
                        is_empty_color = (
                            isinstance(color_info, dict) and
                            color_info.get('colors') == [] and
                            color_info.get('total_count') == 0
                        )

                        # 비어있지 않으면 추가
                        if not is_empty_color:
                            record['color_info'] = color_info
                            color_added_count += 1

                    # tone_info는 항상 추가 (존재하면)
                    if tone_info is not None:
                        record['tone_info'] = tone_info
                        tone_added_count += 1
                else:
                    no_match_count += 1

                # 결과 저장
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"[경고] 원본 파일 {line_num}번째 줄 JSON 파싱 실패: {e}")
                continue

    print(f"\n완료!")
    print(f"총 처리된 레코드: {processed_count}개")
    print(f"color_info 추가된 레코드: {color_added_count}개")
    print(f"tone_info 추가된 레코드: {tone_added_count}개")
    print(f"매칭되지 않은 레코드: {no_match_count}개")
    if processed_count > 0:
        print(f"매칭 비율: {(processed_count - no_match_count)/processed_count*100:.1f}%")


if __name__ == "__main__":
    # 파일 경로 설정
    BASE_DIR = Path(__file__).parent
    COLOR_DIR = BASE_DIR.parent / "color_product"

    # 입력 파일
    source_file = BASE_DIR / "product_data_251225a.jsonl"
    color_tone_file1 = COLOR_DIR / "product_documents_with_tones_RE.jsonl"
    color_tone_file2 = COLOR_DIR / "product_documents_included_tags_with_manycolor_tone.jsonl"

    # 출력 파일 (임시 파일 사용)
    temp_output_file = BASE_DIR / "product_data_251225a_temp.jsonl"
    final_output_file = BASE_DIR / "product_data_251225a.jsonl"

    # 파일 존재 확인
    if not source_file.exists():
        print(f"오류: 원본 파일이 존재하지 않습니다: {source_file}")
        exit(1)

    # 컬러/톤 데이터 로드
    color_tone_map = load_color_tone_data(color_tone_file1, color_tone_file2)

    # 컬러/톤 정보 병합
    merge_color_tone_info(source_file, color_tone_map, temp_output_file)

    # 임시 파일을 최종 파일로 이동
    import shutil
    shutil.move(str(temp_output_file), str(final_output_file))
    print(f"\n최종 파일로 저장 완료: {final_output_file}")
