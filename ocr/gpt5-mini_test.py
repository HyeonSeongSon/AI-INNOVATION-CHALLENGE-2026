from openai import OpenAI

client = OpenAI(api_key="api_key")

image_urls = [
    "https://images-kr.amoremall.com/fileupload/products/111170002324/detail/2025/10/14/PDP_(EC)%20111174855_%EC%9E%90%EC%9D%8C%202%EC%A2%85%20%EC%84%B8%ED%8A%B8%20(1).jpg",
    "https://images-kr.amoremall.com/fileupload/products/111170002324/detail/2025/10/14/PDP_(EC)%20111174855_%EC%9E%90%EC%9D%8C%202%EC%A2%85%20%EC%84%B8%ED%8A%B8%20(2).jpg",
]

# 텍스트 지시문
instruction_text = (
    "당신은 상품이미지에서 정보를 추출하는 AI입니다. "
    "상품정보 이미지를 주면 해당 이미지에서만 정보를 획득하여 "
    "상품의 특징, 성분, 장점 등을 정리합니다. "
    "참고로 당신이 생성한 텍스트는 광고문구 생성에 사용될 rag의 문서가 될 것입니다."
)

# content 배열 생성
content_list = [{"type": "text", "text": instruction_text}]

# 이미지 URL마다 객체 추가
for url in image_urls:
    content_list.append({
        "type": "image_url",
        "image_url": {"url": url}
    })

response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=[
        {
            "role": "user",
            "content": content_list
        }
    ]
)

print(response.choices[0].message.content)