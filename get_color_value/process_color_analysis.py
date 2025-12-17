"""
JSONL 파일에서 색상 이미지 URL을 읽어 GPT로 분석하고 결과를 저장하는 스크립트
"""

import json
import os
import time
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


def ask_gpt_with_image_url(image_url, question, api_key=None):
    """
    이미지 URL과 함께 GPT에 질문하기

    Args:
        image_url (str): 질문할 이미지 URL
        question (str): 이미지에 대한 질문
        api_key (str, optional): OpenAI API 키. None이면 환경변수에서 가져옴

    Returns:
        str: GPT의 응답
    """
    # API 키 설정
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("API 키가 설정되지 않았습니다. 환경변수 OPENAI_API_KEY를 설정하거나 api_key 파라미터를 전달하세요.")

    # 이미지 URL 확인
    if not image_url or not isinstance(image_url, str):
        raise ValueError(f"유효하지 않은 이미지 URL입니다: {image_url}")

    # OpenAI 클라이언트 초기화
    client = OpenAI(api_key=api_key)

    # API 호출
    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": question
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

    return response.choices[0].message.content


def load_jsonl(input_file):
    """
    JSONL 파일을 읽어서 리스트로 반환

    Args:
        input_file (str): 입력 파일 경로

    Returns:
        list: JSON 객체 리스트
    """
    data = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data_list, output_file):
    """
    리스트를 JSONL 파일로 저장

    Args:
        data_list (list): 저장할 데이터 리스트
        output_file (str): 출력 파일 경로
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for data in data_list:
            json_line = json.dumps(data, ensure_ascii=False)
            f.write(json_line + '\n')


def analyze_color_from_jsonl(input_file, output_file):
    """
    JSONL 파일에서 색상 이미지를 읽어 GPT로 분석하고 결과를 저장

    Args:
        input_file (str): 입력 JSONL 파일 경로
        output_file (str): 출력 JSONL 파일 경로

    Returns:
        list: 업데이트된 상품 리스트
    """
    # JSONL 파일 읽기
    print(f"파일 읽는 중: {input_file}")
    products = load_jsonl(input_file)
    print(f"총 {len(products)}개의 상품 발견\n")

    # 색상 분석 질문
    question = """당신은 뷰티 상품의 색상 분석 전문가입니다.

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

    updated_products = []

    for product_idx, product in enumerate(products, 1):
        print(f"\n{'='*60}")
        print(f"[{product_idx}/{len(products)}] 상품 분석 시작")
        print(f"{'='*60}")
        print(f"상품명: {product.get('상품명', 'N/A')}")

        # color_info가 있는지 확인
        color_info = product.get('color_info', {})
        colors = color_info.get('colors', [])

        if not colors:
            print("⚠ 색상 정보가 없습니다. 건너뜁니다.")
            updated_products.append(product)
            continue

        print(f"총 {len(colors)}개의 색상 분석 중...")

        # 각 색상에 대해 GPT 분석
        for color_idx, color_item in enumerate(colors, 1):
            color_name = color_item.get('color_name', 'Unknown')
            image_url = color_item.get('image_url', '')

            if not image_url:
                print(f"  [{color_idx}/{len(colors)}] {color_name}: 이미지 URL 없음, 건너뜀")
                color_item['color_value'] = None
                continue

            try:
                print(f"  [{color_idx}/{len(colors)}] {color_name} 분석 중...")

                # GPT에게 이미지 분석 요청
                gpt_response = ask_gpt_with_image_url(image_url, question)

                # JSON 파싱 시도
                try:
                    # GPT 응답에서 JSON 부분만 추출 (마크다운 코드 블록 제거)
                    if '```json' in gpt_response:
                        json_str = gpt_response.split('```json')[1].split('```')[0].strip()
                    elif '```' in gpt_response:
                        json_str = gpt_response.split('```')[1].split('```')[0].strip()
                    else:
                        json_str = gpt_response.strip()

                    color_value = json.loads(json_str)
                    color_item['color_value'] = color_value
                    print(f"  ✓ 분석 완료: HEX={color_value.get('color', {}).get('hex', 'N/A')}")

                except json.JSONDecodeError as e:
                    print(f"  ⚠ JSON 파싱 실패: {e}")
                    # 원본 응답을 문자열로 저장
                    color_item['color_value'] = {"raw_response": gpt_response}

                # API Rate Limit 방지를 위한 대기
                time.sleep(1)

            except Exception as e:
                print(f"  ✗ 분석 실패: {e}")
                color_item['color_value'] = None

        updated_products.append(product)

        # 다음 상품으로 이동하기 전 잠시 대기
        if product_idx < len(products):
            time.sleep(2)

    # 결과 저장
    print(f"\n결과 저장 중: {output_file}")
    save_jsonl(updated_products, output_file)

    return updated_products


def main():
    """메인 실행 함수"""
    # 입력/출력 파일 경로
    input_file = "./data/crawling_result/add_coler_image_test.jsonl"
    output_file = "./data/crawling_result/add_coler_image_value_test.jsonl"

    print("=" * 60)
    print("색상 이미지 분석 시작")
    print("=" * 60)

    # JSONL 파일에서 색상 이미지를 읽어 분석
    results = analyze_color_from_jsonl(input_file, output_file)

    # 최종 결과 출력
    print("\n" + "=" * 60)
    print("분석 완료!")
    print("=" * 60)
    print(f"✓ 저장 위치: {output_file}")
    print(f"✓ 총 상품 수: {len(results)}개")

    # 통계
    total_colors = 0
    analyzed_colors = 0

    for product in results:
        colors = product.get('color_info', {}).get('colors', [])
        total_colors += len(colors)
        analyzed_colors += sum(1 for c in colors if c.get('color_value') is not None)

    print(f"✓ 총 색상 수: {total_colors}개")
    print(f"✓ 분석된 색상: {analyzed_colors}개")

    # 분석된 색상 예시
    print("\n=== 분석 예시 (최대 3개) ===")
    count = 0
    for product in results:
        if count >= 3:
            break

        colors = product.get('color_info', {}).get('colors', [])
        for color in colors:
            if color.get('color_value') and count < 3:
                print(f"\n{count + 1}. 상품: {product.get('상품명', 'N/A')}")
                print(f"   색상명: {color.get('color_name', 'N/A')}")
                color_value = color.get('color_value', {})
                if 'color' in color_value:
                    print(f"   HEX: {color_value['color'].get('hex', 'N/A')}")
                    print(f"   RGB: {color_value['color'].get('rgb', 'N/A')}")
                count += 1
                if count >= 3:
                    break


if __name__ == "__main__":
    main()
