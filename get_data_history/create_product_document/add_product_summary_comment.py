"""
JSONL 파일의 각 제품에 LLM이 생성한 한 줄 소개를 추가하는 스크립트
"""

import json
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# .env 로드
load_dotenv()

def generate_one_line_summary(brand: str, product_name: str, document: str, llm) -> str:
    """
    상품명, 브랜드, 문서 정보를 바탕으로 한 줄 소개 생성

    Args:
        brand: 브랜드명
        product_name: 상품명
        document: 상품 상세 문서
        llm: ChatOpenAI 인스턴스

    Returns:
        한 줄 소개 문구
    """
    prompt = f"""
아래 상품명과 문서내용을 바탕으로 해당 제품의 간략한 한문장 설명 코멘트를 작성해주세요.

**상품명**: {product_name}

**문서내용**: {document}

**작성 가이드:**
1. **핵심만 간결하게**: 60~80자 내외로 작성하세요. 모든 정보를 담으려 하지 말고 가장 중요한 2~3가지 특징만 선택하세요.
2. 문서 내용에 담긴 구체적인 특징(텍스처, 지속력, 성분, 효과 등) 중 가장 차별화된 포인트를 활용하세요.
3. 제품의 핵심 기능과 사용감, 효능을 자연스럽게 연결하여 한 문장으로 표현하세요.
4. **문장 끝**: 반드시 구체적인 제품 종류로 종결하되, "입니다"를 붙이지 말고 체언으로 끝내세요. (예: "~유지해주는 아이라이너", "~선사하는 하이라이터", "~완성하는 헤어 아이롱")
5. 인체적용시험이나 특수 테스트 결과는 1~2개만 선택적으로 언급하세요.
6. 따옴표나 부가 설명 없이 순수한 문구만 작성하세요.

**좋은 예시:**
- "부드럽고 탄성 좋은 브러시로 눈꼬리까지 끊김 없이 그려지며, 1초 픽싱과 24시간 지속력으로 물·오일에도 번짐 없이 또렷한 라인을 유지해주는 아이라이너"
- "미세한 펄 입자가 피부 결을 따라 자연스럽게 밀착되어 촉촉한 광채를 선사하며, 저자극 성분으로 민감 피부도 안심하고 사용할 수 있는 하이라이터"

**나쁜 예시 (피해야 할 스타일):**
- "완벽한 메이크업 완성!" (너무 단편적, 구체성 없음)
- "24시간 지속" (문장이 아님)
- "최고의 아이라이너" (추상적, 근거 없음)
""".strip()

    try:
        response = llm.invoke(prompt)
        summary = response.content.strip()
        # 따옴표 제거
        summary = summary.strip('"').strip("'")
        return summary
    except Exception as e:
        print(f"[ERROR] LLM 호출 실패: {e}")
        return f"{brand} {product_name}"


def process_jsonl_file(input_path: str, output_path: str, api_key: str):
    """
    JSONL 파일을 읽어서 각 제품에 한 줄 소개를 추가하고 새 파일로 저장

    Args:
        input_path: 입력 JSONL 파일 경로
        output_path: 출력 JSONL 파일 경로
        api_key: OpenAI API 키
    """
    # LLM 초기화
    llm = ChatOpenAI(
        model="gpt-5-mini",
        temperature=0.7,
        api_key=api_key
    )

    processed_count = 0
    error_count = 0

    print(f"[INFO] 입력 파일: {input_path}")
    print(f"[INFO] 출력 파일: {output_path}")
    print("=" * 80)

    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:

        for line_num, line in enumerate(infile, 1):
            try:
                # JSON 파싱
                product = json.loads(line.strip())

                # 필수 필드 확인
                brand = product.get('브랜드', '')
                product_name = product.get('상품명', '')
                document = product.get('문서', '')

                if not all([brand, product_name, document]):
                    print(f"[WARNING] 라인 {line_num}: 필수 필드 누락, 스킵")
                    error_count += 1
                    continue

                # 한 줄 소개 생성
                print(f"\n[{line_num}] {brand} - {product_name[:50]}...")
                one_line_summary = generate_one_line_summary(brand, product_name, document, llm)
                print(f"    → {one_line_summary}")

                # 제품 데이터를 순서대로 재구성 ('문서' 다음에 '한줄소개' 추가)
                ordered_product = {}
                for key, value in product.items():
                    ordered_product[key] = value
                    if key == '문서':
                        ordered_product['한줄소개'] = one_line_summary

                # 출력 파일에 저장
                outfile.write(json.dumps(ordered_product, ensure_ascii=False) + '\n')
                processed_count += 1

            except json.JSONDecodeError as e:
                print(f"[ERROR] 라인 {line_num}: JSON 파싱 실패 - {e}")
                error_count += 1
            except Exception as e:
                print(f"[ERROR] 라인 {line_num}: 처리 중 오류 - {e}")
                error_count += 1

    print("\n" + "=" * 80)
    print(f"[완료] 총 {processed_count}개 제품 처리 완료")
    print(f"[완료] 에러: {error_count}개")
    print(f"[완료] 결과 파일: {output_path}")


if __name__ == "__main__":
    # 설정
    INPUT_FILE = "product_data_251227.jsonl"
    OUTPUT_FILE = "product_data_251227_with_summary.jsonl"

    # API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

    # 현재 스크립트 디렉토리 기준 파일 경로
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, INPUT_FILE)
    output_path = os.path.join(script_dir, OUTPUT_FILE)

    # 입력 파일 존재 확인
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    # 처리 시작
    print("=== 제품 한 줄 소개 생성 시작 ===\n")
    process_jsonl_file(input_path, output_path, api_key)
