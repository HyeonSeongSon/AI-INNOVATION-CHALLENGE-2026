"""
상품별 컬러 톤 분석 스크립트

각 상품의 컬러들을 분석하여 어떤 톤(웜톤, 쿨톤 등)에 해당하는지 LLM으로 판단

사용법:
    python analyze_color_tones.py

필요한 패키지:
    pip install openai python-dotenv
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 기준 톤 리스트
TONE_CATEGORIES = [
    "웜톤",
    "봄웜톤",
    "가을웜톤",
    "쿨톤",
    "여름쿨톤",
    "겨울쿨톤",
    "뉴트럴톤"
]


def analyze_product_tones(hex_colors: List[str], product_name: str = "") -> Dict[str, Any]:
    """
    LLM을 사용하여 상품의 HEX 컬러 리스트를 분석하여 톤 분류

    Args:
        hex_colors: HEX 컬러 코드 리스트
        product_name: 상품명 (디버깅용)

    Returns:
        톤 분석 결과 딕셔너리
    """
    if not hex_colors:
        return {
            "tones": [],
            "error": "컬러 정보 없음"
        }

    print(f"상품 톤 분석 중: {product_name} (컬러 {len(hex_colors)}개)")

    # API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "tones": [],
            "error": "OPENAI_API_KEY가 설정되지 않았습니다"
        }

    # HEX 컬러 리스트를 문자열로 변환
    colors_str = ", ".join(hex_colors)

    try:
        # OpenAI 클라이언트 초기화
        client = OpenAI(api_key=api_key)

        # GPT API 호출
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": f"""당신은 화장품 색상 톤 분석 전문가입니다.

아래 화장품 제품의 HEX 컬러 리스트를 분석하여, 이 제품 라인업에 포함된 모든 톤을 찾아주세요.

**컬러 리스트:**
{colors_str}

**기준 톤:**
- 웜톤 (따뜻한 톤)
- 봄웜톤 (밝고 선명한 웜톤)
- 가을웜톤 (깊고 차분한 웜톤)
- 쿨톤 (차가운 톤)
- 여름쿨톤 (부드럽고 차분한 쿨톤)
- 겨울쿨톤 (선명하고 강렬한 쿨톤)
- 뉴트럴톤 (중립 톤)

**출력 규칙:**
- 반드시 JSON만 출력하세요
- 설명 문장, 주석, 마크다운 금지
- 제품 라인업에 해당하는 모든 톤을 포함하세요
- 해당하지 않는 톤은 포함하지 마세요

**출력 형식:**
{{
  "tones": ["웜톤", "봄웜톤", ...]
}}"""
                }
            ],
            max_completion_tokens=500
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

        tone_info = json.loads(response_text)
        tones = tone_info.get("tones", [])

        print(f"  → 분석 완료: {', '.join(tones) if tones else '톤 없음'}")

        return {
            "tones": tones
        }

    except json.JSONDecodeError as e:
        print(f"  → JSON 파싱 실패: {e}")
        return {
            "tones": [],
            "error": f"JSON 파싱 실패: {str(e)}"
        }
    except Exception as e:
        print(f"  → 톤 분석 실패: {e}")
        return {
            "tones": [],
            "error": str(e)
        }


def process_jsonl_file(
    input_file,
    output_file,
    max_records: int = None,
    delay_seconds: float = 2.0
) -> None:
    """
    JSONL 파일을 읽어 각 상품의 컬러 톤을 분석

    Args:
        input_file: 입력 JSONL 파일 경로 (컬러 추출 완료된 파일)
        output_file: 출력 JSONL 파일 경로
        max_records: 처리할 최대 레코드 수 (None이면 전체 처리)
        delay_seconds: 각 API 호출 사이의 대기 시간 (초, 기본값: 2.0)
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
    skipped_count = 0

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
                if 'color_info' not in record or 'colors' not in record['color_info']:
                    print(f"  ⚠️ color_info 없음 - 건너뜀")
                    skipped_count += 1
                    # 원본 그대로 저장
                    outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                    continue

                colors = record['color_info']['colors']

                # HEX 컬러 추출
                hex_colors = []
                for color_item in colors:
                    if 'extracted_color' in color_item and 'color' in color_item['extracted_color']:
                        hex_value = color_item['extracted_color']['color'].get('hex')
                        if hex_value:
                            hex_colors.append(hex_value)

                if not hex_colors:
                    print(f"  ⚠️ 추출된 컬러 없음 - 건너뜀")
                    skipped_count += 1
                    # 원본 그대로 저장
                    outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                    continue

                # 톤 분석
                product_name = record.get('상품명', '')
                tone_result = analyze_product_tones(hex_colors, product_name)

                # 결과를 tone_info로 추가 (톤 리스트만)
                record['tone_info'] = tone_result.get('tones', [])

                # 결과 저장
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                processed_count += 1

                # Rate limit 방지를 위한 지연
                time.sleep(delay_seconds)

            except json.JSONDecodeError as e:
                print(f"  경고: JSON 파싱 실패 (라인 {line_num}): {e}")
            except Exception as e:
                print(f"  에러: 처리 실패 (라인 {line_num}): {e}")

    print("\n" + "=" * 80)
    print(f"처리 완료!")
    print(f"  - 처리된 레코드: {processed_count}")
    print(f"  - 건너뛴 레코드: {skipped_count}")
    print(f"  - 출력 파일: {output_file}")
    print("=" * 80)


def main():
    """메인 함수"""
    # 파일 경로 설정 (스크립트 위치 기준)
    script_dir = Path(__file__).parent
    input_file = script_dir / "product_documents_with_extracted_colors_RE.jsonl"
    output_file = script_dir / "product_documents_with_tones_RE.jsonl"

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
        delay_seconds=2.0      # 2초 대기 (Rate limit 방지)
    )


if __name__ == "__main__":
    main()
