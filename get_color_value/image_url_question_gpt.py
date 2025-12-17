import os
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def ask_gpt_with_image_url(image_url, question, api_key=None):
    """
    이미지 URL과 함께 GPT-4o-mini에 질문하기

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

def main():
    """사용 예시"""
    # 이미지 URL (웹상의 이미지 주소)
    image_url = "https://images-kr.amoremall.com/unitproducts/111572143/111572143_01.png?1724916203057"

    # 질문
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

    try:
        # GPT에 질문
        print(f"이미지 URL: {image_url}")
        print(f"질문: {question}")
        print("\nGPT 응답:")
        print("-" * 50)

        answer = ask_gpt_with_image_url(image_url, question)
        print(answer)

    except ValueError as e:
        print(f"오류: {e}")
        print("\nAPI 키 설정 방법:")
        print("1. OpenAI API 키를 발급받으세요 (https://platform.openai.com/api-keys)")
        print("2. .env 파일을 생성하고 다음 내용을 추가하세요:")
        print("   OPENAI_API_KEY=your-api-key-here")
        print("3. python-dotenv 설치: pip install python-dotenv")

    except Exception as e:
        print(f"예상치 못한 오류: {e}")

if __name__ == "__main__":
    main()
