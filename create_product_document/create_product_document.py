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
    with open(r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\crawling_result\product_crawling_251217.jsonl', 'r', encoding='utf-8') as f:
      data = [json.loads(line) for line in f]
    return data
  
  def create_content_list(self, product: Dict):
    """상품 분석 프롬프트 생성"""
    brand = product.get('브랜드', '')
    product_name = product.get('상품명', '')

    prompt = f"""당신은 '퍼포먼스 마케팅 전문 콘텐츠 기획자'이자 '화장품 성분 분석가'입니다.

[역할 정의]
본 프롬프트에 작성된 내용은 '상품 정보 문서'의 역할을 합니다. 따라서 아래의 [상품 정보] 및 가이드라인을 기준 문서로 삼아 분석 및 기획을 진행해 주세요.
제공된 상품 상세 이미지를 분석하여, 매력적인 광고 카피와 상세페이지 기획안을 작성할 수 있도록 핵심 정보를 구조화하여 정리해주세요.

[상품 정보]
브랜드: {brand}
상품명: {product_name}

[분석 범위 제한]
- 분석 대상은 제공된 상품 상세 이미지에서 추출된 내용으로 한정합니다.
- 외부 지식, 브랜드 일반 정보, 화장품 상식 사용 금지
- 이미지에 없는 정보는 반드시 "없음"으로 표기

[작성 원칙]
- 정보가 이미지의 어느 위치에 있었는지에 대한 설명은 작성하지 않습니다.
  (예: "그래프 옆에 표기됨", "타이틀 영역에 용량 표시" 등 위치·레이아웃 언급 금지)
- 이미지 내 텍스트 내용 자체만을 정보로 정리하며,
  디자인 구성, 배치, 시각적 위치에 대한 메타 설명은 제외합니다.
- 동일한 내용이 여러 이미지에 반복되어 나타날 경우,
  의미 단위 기준으로 한 번만 정리합니다.
- 특수 문자 사용은 최소화합니다.

[분석 원칙]
1. Fact & Feeling
- 성분, 수치, 용량 등 팩트 정보는 이미지 표기 그대로 추출
- 감성/느낌 표현은 이미지 내 문구에서 직접 확인되는 표현만 발췌

2. Strict Accuracy
- 추측, 보완 설명, 일반화 금지
- 임상/효능 수치는 원문 그대로 보존(날조 금지)

3. Copywriting Source
- 광고 문구로 바로 활용 가능한 키워드/문장을 우선 추출

[출력 형식]
다음 항목에 맞춰 정보를 정리하여 출력하세요.

1) 핵심 훅킹 - 메인 카피 & 캐치프레이즈
- 이미지에서 가장 크게 강조된 헤드 카피
- 소비자의 이목을 끄는 서브 카피 및 슬로건
- 강조된 해시태그(#)나 키워드

2) 감각/제형 - 텍스처 & 사용감 묘사
- 제형을 묘사하는 구체적 형용사 (예: 셔벗 같은, 쫀쫀한, 물처럼 흐르는)
- 발림성, 흡수력, 마무리감 표현 (예: 끈적임 없이 산뜻, 속당김 해결)
- 향(Scent) 묘사 있는 경우

3) 소구 포인트 - 타겟 고민 & 해결책
- 타겟팅하는 구체적인 피부/모발 고민 (예: 넓어진 모공, 푸석한 머릿결)
- 브랜드가 제시하는 해결 방식 (어떤 원리로 개선하는지)
- 타겟 연령층이나 특정 상황 (예: 화장 잘 먹고 싶은 날, 예민한 날)

4) 신뢰도/입증 - 임상 수치 & 수상 내역
- 구체적인 임상 실험 결과 수치 (예: 모공 부피 -26.5%, 각질 99% 개선)
- 소비자 만족도, 재구매율, 평점 (예: 4.9/5.0, 누적 판매 22만 개)
- 뷰티 어워드 수상 내역, 랭킹 1위 정보

5) 성분 스토리 - 핵심 원료 & 효능 
- 메인 성분명과 마케팅 용어 (예: 3초 진정 시카, 청정 대나무 숯)
- 해당 성분이 피부에 주는 구체적 이점 (이미지 내 설명 기준)
- 특허 기술이나 공법 명칭

6) 사용 경험 - 사용법 & 루틴
- 권장 사용 순서 (STEP별 요약)
- 효과를 극대화하는 꿀팁 (Tip)
- 용기(패키지)의 특징이나 편리성 (예: 원터치 캡, 스포이드)

7) 구매 혜택 - 구성 및 패키지 정보
- 세트 구성품 상세 (본품 + 증정품 용량 포함)
- 포장/선물 관련 정보 (친환경 패키지, 선물 박스 제공 등)

8) 근거 원문 보존 (Legal-safe)
- 임상/효능 관련 이미지 내 문구 원문 전체
- 각 문구 옆에 이미지 위치(예: 상단 배너 / 하단 표기)

9) 정규화 요약 (RAG/DB용)
- category:
- main_benefits:
- key_ingredients:
- texture_keywords:
- target_concerns:
- numeric_claims:
"""

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
    model="gpt-5.1",
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
    failed_data = []  # 실패한 데이터 저장

    # 진행률 추적 변수
    total_count = len(self.data)
    success_count = 0
    failed_count = 0
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"상품 문서 생성 시작")
    print(f"총 처리 대상: {total_count}개")
    print(f"{'='*60}\n")

    for idx, data in enumerate(self.data, 1):
      try:
        content_list = self.create_content_list(data)

        # GIF 파일 제외
        image_urls = [url for url in data['상품상세_이미지'] if not url.lower().endswith('.gif')]

        content_list = self.append_url(content_list, image_urls)
        response = self.create_document(content_list)

        # 응답에서 필요한 정보 추출
        result_data = {
          '브랜드': data.get('브랜드', ''),
          '상품명': data.get('상품명', ''),
          '생성된_문서': response.choices[0].message.content,
          '생성_시간': datetime.now().isoformat()
        }
        result.append(result_data)
        success_count += 1

        # 진행률 계산
        progress_percent = (idx / total_count) * 100
        elapsed_time = time.time() - start_time
        avg_time_per_item = elapsed_time / idx
        estimated_remaining = avg_time_per_item * (total_count - idx)

        print(f"[{idx}/{total_count}] ({progress_percent:.1f}%) 성공: {data.get('상품명', 'Unknown')[:40]}")
        print(f"  → 성공: {success_count} | 실패: {failed_count} | 경과: {elapsed_time:.1f}초 | 예상 남은 시간: {estimated_remaining:.1f}초\n")

      except Exception as e:
        # 실패한 원본 데이터 저장
        failed_data.append(data)
        failed_count += 1

        # 진행률 계산
        progress_percent = (idx / total_count) * 100
        elapsed_time = time.time() - start_time
        avg_time_per_item = elapsed_time / idx
        estimated_remaining = avg_time_per_item * (total_count - idx)

        print(f"[{idx}/{total_count}] ({progress_percent:.1f}%) 실패: {data.get('상품명', 'Unknown')[:40]}")
        print(f"  → 오류: {str(e)[:60]}")
        print(f"  → 성공: {success_count} | 실패: {failed_count} | 경과: {elapsed_time:.1f}초 | 예상 남은 시간: {estimated_remaining:.1f}초\n")

      time.sleep(1)

    # 총 소요 시간 계산
    total_time = time.time() - start_time
    avg_time_per_success = total_time / success_count if success_count > 0 else 0

    # 성공한 결과를 jsonl 파일로 저장
    output_path = r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\create_product_document\product_documents.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
      for item in result:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

    # 최종 요약 출력
    print(f"\n{'='*60}")
    print(f"상품 문서 생성 완료")
    print(f"{'='*60}")
    print(f"총 처리 대상: {total_count}개")
    print(f"성공: {success_count}개 ({(success_count/total_count*100):.1f}%)")
    print(f"실패: {failed_count}개 ({(failed_count/total_count*100):.1f}%)")
    print(f"총 소요 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
    print(f"평균 처리 시간: {avg_time_per_success:.1f}초/개")
    print(f"{'='*60}")
    print(f"성공 파일 저장: {output_path}")

    # 실패한 데이터를 jsonl 파일로 저장
    if failed_data:
      failed_path = r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\create_product_document\failed_products.jsonl'
      with open(failed_path, 'w', encoding='utf-8') as f:
        for item in failed_data:
          f.write(json.dumps(item, ensure_ascii=False) + '\n')

      print(f"실패 파일 저장: {failed_path}")

    print(f"{'='*60}\n")

    return result

if __name__ == "__main__":
  pdg = ProductDocumentGenerator()
  pdg.main()