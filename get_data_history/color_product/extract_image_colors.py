"""
이미지 URL에서 컬러값을 추출하여 JSONL 파일에 추가하는 스크립트

사용법:
    python extract_image_colors.py

필요한 패키지:
    pip install openai python-dotenv
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


def extract_color_from_image(image_url: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    GPT Vision API를 사용하여 이미지 URL에서 주요 컬러 정보 추출

    Args:
        image_url: 분석할 이미지 URL
        max_retries: Rate limit 에러 발생 시 최대 재시도 횟수

    Returns:
        컬러 정보 딕셔너리
    """
    print(f"이미지 컬러 추출 중: {image_url}")

    # API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "error": "OPENAI_API_KEY가 설정되지 않았습니다",
            "color": None
        }

    for attempt in range(max_retries):
        try:
            # OpenAI 클라이언트 초기화
            client = OpenAI(api_key=api_key)

            # GPT Vision API 호출
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """당신은 뷰티 상품의 색상 분석 전문가입니다.

아래 이미지에서 "색조 제품의 색상 부분만" 분석하세요.
(패키지, 케이스, 배경 색상은 반드시 제외)

출력 규칙:
- 반드시 JSON만 출력하세요
- 설명 문장, 주석, 마크다운 금지
- 값이 불확실하더라도 null 없이 숫자로 출력

출력 형식:
{
  "color": {
    "hex": "#000000",
    "rgb": [0, 0, 0],
    "hsv": { "h": 0, "s": 0, "v": 0 },
    "lab": { "l": 0.0, "a": 0.0, "b": 0.0 }
  }
}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=1000
            )

            # 응답 텍스트 파싱
            response_text = response.choices[0].message.content.strip()

            # JSON 추출 (```json 마크다운 블록 처리)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            color_info = json.loads(response_text)
            hex_color = color_info.get("color", {}).get("hex", "N/A")
            print(f"  → 추출 완료: {hex_color}")

            return color_info

        except json.JSONDecodeError as e:
            print(f"  → JSON 파싱 실패: {e}")
            return {
                "error": f"JSON 파싱 실패: {str(e)}",
                "color": None
            }
        except Exception as e:
            error_message = str(e)

            # Rate limit 에러 체크
            if "rate_limit" in error_message.lower() or "429" in error_message:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 5초, 10초, 15초 등으로 증가
                    print(f"  → Rate limit 도달. {wait_time}초 대기 후 재시도... ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  → Rate limit 에러: 최대 재시도 횟수 도달")
            else:
                print(f"  → 컬러 추출 실패: {e}")

            return {
                "error": error_message,
                "color": None
            }

    return {
        "error": "최대 재시도 횟수 초과",
        "color": None
    }


def process_jsonl_file(
    input_file,
    output_file,
    max_records: int = None,
    delay_seconds: float = 3.0
) -> None:
    """
    JSONL 파일을 읽어 각 color_info의 colors 리스트에 있는 이미지에서 컬러 추출

    Args:
        input_file: 입력 JSONL 파일 경로 (str 또는 Path)
        output_file: 출력 JSONL 파일 경로 (str 또는 Path)
        max_records: 처리할 최대 레코드 수 (None이면 전체 처리)
        delay_seconds: 각 API 호출 사이의 대기 시간 (초, 기본값: 3.0)
    """
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")
    print("-" * 80)

    input_path = Path(input_file) if isinstance(input_file, str) else input_file
    output_path = Path(output_file) if isinstance(output_file, str) else output_file

    if not input_path.exists():
        print(f"에러: 입력 파일이 존재하지 않습니다: {input_file}")
        return

    # 출력 파일 디렉토리 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    total_images = 0

    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            # max_records 체크
            if max_records and processed_count >= max_records:
                print(f"\n최대 레코드 수({max_records})에 도달했습니다.")
                break

            try:
                # JSON 파싱
                record = json.loads(line.strip())

                print(f"\n[{line_num}] 처리 중: {record.get('브랜드', 'N/A')} - {record.get('상품명', 'N/A')}")

                # color_info 확인
                if 'color_info' in record and 'colors' in record['color_info']:
                    colors = record['color_info']['colors']

                    print(f"  총 {len(colors)}개 색상 변형 발견")

                    # 각 색상의 이미지에서 컬러 추출
                    for idx, color_item in enumerate(colors):
                        if 'image_url' in color_item:
                            total_images += 1
                            color_name = color_item.get('color_name', f'Color {idx+1}')
                            print(f"  [{idx+1}/{len(colors)}] {color_name}")

                            # 컬러 추출
                            extracted_color = extract_color_from_image(color_item['image_url'])

                            # 원본 데이터에 추가
                            color_item['extracted_color'] = extracted_color

                            # Rate limit 방지를 위한 지연
                            time.sleep(delay_seconds)

                # 결과 저장
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"  경고: JSON 파싱 실패 (라인 {line_num}): {e}")
            except Exception as e:
                print(f"  에러: 처리 실패 (라인 {line_num}): {e}")

    print("\n" + "=" * 80)
    print(f"처리 완료!")
    print(f"  - 처리된 레코드: {processed_count}")
    print(f"  - 분석된 이미지: {total_images}")
    print(f"  - 출력 파일: {output_file}")
    print("=" * 80)


def main():
    """메인 함수"""
    # 파일 경로 설정 (스크립트 위치 기준)
    script_dir = Path(__file__).parent
    input_file = script_dir / "product_documents_included_tags_with_color_RE.jsonl"
    output_file = script_dir / "product_documents_with_extracted_colors_RE.jsonl"

    # API 키 확인
    if not os.environ.get("OPENAI_API_KEY"):
        print("에러: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("'.env' 파일에 OPENAI_API_KEY를 설정하거나 환경 변수로 설정해주세요.")
        return

    # 처리 실행
    # max_records: 처리할 최대 레코드 수 (None=전체)
    # delay_seconds: API 호출 간격 (초) - Rate limit 방지용
    process_jsonl_file(
        input_file=input_file,
        output_file=output_file,
        max_records=None,      # 전체 처리, 테스트 시 3 등으로 변경
        delay_seconds=3.0      # 3초 대기 (Rate limit 방지)
    )


if __name__ == "__main__":
    main()
