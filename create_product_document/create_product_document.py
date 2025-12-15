from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import time

load_dotenv()

class ProductDocumentGenerator:
  """
  상품 문서 생성기
  """
  def __init__(self):
    """
    OpenAI API 클라이언트 초기화
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    self.client = OpenAI(api_key=api_key)
    self.data = self.load_data()

  def load_data(self):
    # 문서 추출할 jsonl 파일 경로
    with open(r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\crawling_result\test.jsonl', 'r', encoding='utf-8') as f:
      data = [json.loads(line) for line in f]
    return data
  
  def create_content_list(self, product: Dict):
    """상품 분석 프롬프트 생성"""
    brand = product.get('브랜드', '')
    product_name = product.get('상품명', '')

    prompt = f"""당신은 한국 화장품/뷰티 상품 분석 전문가입니다.
다음 상품의 상세 이미지를 분석하여 정확한 정보를 추출해주세요.

[상품 정보]
- 브랜드: {brand}
- 상품명: {product_name}

[분석 지침]
1. 이미지에 표기된 텍스트, 수치, 성분만 정확히 추출
2. 이미지에 없는 내용은 절대 추측 금지
3. 숫자, 퍼센트, 성분 비율은 정확히 기록
4. 세트 상품인 경우 구성품 모두 나열

[출력 형식]
아래 형식을 정확히 따라 번호와 함께 출력하세요:

1) 제품·세트 정보
브랜드: {brand}
제품명(이미지 표기): (이미지에 보이는 정확한 제품명)
세트 구성(이미지 표기): (세트라면 본품·견본 구분하여 나열, 단품이면 용량만)

2) 라인 콘셉트 / 포지셔닝 (이미지 표기)
(이미지에 표기된 콘셉트, 캐치프레이즈)
(예: "건강한 웰에이징 케어의 시작" / Journey to Holistic Beauty)
(판매 순위, 수상 내역 등이 있으면 기재)
(목표 피부 고민, 타깃 연령대 등)

3) 제품별 기능·텍스처·사용 순서 (이미지의 STEP 설명)
(STEP 1, STEP 2 형식으로 있으면 그대로 기재)
(각 제품별 특징: 텍스처, 흡수감, 역할)
(사용 순서가 명시되어 있으면 순서대로 나열)

4) 핵심 성분·기술 (이미지 표기)
(이미지에 표기된 모든 성분명, 복합체명)
(특허 기술, 독자 기술 명칭)
(예: "AP 세라 CMC 콤플렉스™", "순간 흡수 기술")

5) 주된 효능·타깃 고민 (이미지 표기)
(보습, 진정, 장벽, 탄력, 미백, 주름개선 등)
(이미지에서 강조하는 피부 고민 해결 포인트)

6) 임상·사용 결과(이미지에 표기된 수치 요약)
(7일, 4주 등 기간별 수치가 있으면 모두 기재)
(예: 7일 사용 시: +29%, +26%, +37%, +34%)
(예: 4주 사용 시: 90%대~96%대 개선 만족도)
(측정 항목명도 함께 기재)

7) 추가 강조 사항(이미지 표기)
(이미지에서 강조된 특별한 메시지)
(예: "강력한 항산화 효과", "새로운 항산화 성분")

8) 사용법 요약(이미지 기반 권장 루틴)
(제품 사용 순서)
(각 단계별 역할 요약)

9) 마케팅/패키지 정보
(선물세트 제안, 다른 세트와의 비교)
(특별 구성, 한정판 여부 등)

참고(표기 유의사항)
위 내용은 첨부 이미지에 명시된 텍스트와 그래픽을 바탕으로 정리한 것입니다.
이미지에 작은 글씨로 표기된 임상측정 항목의 정확한 명칭·측정 방법 등은 이미지 확대·원문 자료 확인 시 더 구체화할 수 있습니다.

중요: 이미지에 없는 내용은 절대 작성하지 마세요. 해당 항목이 이미지에 없으면 "(이미지에 해당 정보 없음)"이라고 표기하세요."""

    # content 배열 생성
    content_list = [{"type": "text", "text": prompt}]

    return content_list
  
  def append_url(self, content_list, image_urls):
    for url in image_urls:
      content_list.append({
          "type": "image_url",
          "image_url": {"url": url}
      })
    return content_list
  
  def create_document(self, content_list):
    response = self.client.chat.completions.create(
    model="gpt-5-mini",
    messages=[
        {
            "role": "user",
            "content": content_list
        }
    ]
)
    return response
  
  def main(self):
    result = []
    for data in self.data:
      content_list = self.create_content_list(data)
      content_list = self.append_url(content_list, data['상품상세_이미지'])
      response = self.create_document(content_list)

      # 응답에서 필요한 정보 추출
      result_data = {
        '브랜드': data.get('브랜드', ''),
        '상품명': data.get('상품명', ''),
        '생성된_문서': response.choices[0].message.content,
        '생성_시간': datetime.now().isoformat()
      }
      result.append(result_data)
      time.sleep(1)

    # 결과를 jsonl 파일로 저장
    output_path = r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\create_product_document\product_documents.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
      for item in result:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"총 {len(result)}개의 상품 문서가 생성되었습니다.")
    print(f"저장 경로: {output_path}")

    return result

if __name__ == "__main__":
  pdg = ProductDocumentGenerator()
  pdg.main()