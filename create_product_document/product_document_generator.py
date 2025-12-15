"""
상품 이미지 기반 문서 생성 시스템
OpenAI GPT-4 Vision을 사용하여 상품 상세 이미지를 분석하고 구조화된 문서를 생성합니다.

[이미지 처리 방식]
1. Direct URL 방식 (기본): OpenAI가 직접 이미지 다운로드 (빠르고 간단)
2. Base64 방식 (폴백): 우리가 직접 다운로드 후 인코딩 (느린 서버 대응)
   - timeout 발생시 자동으로 Base64 방식으로 재시도
"""

import json
import os
import time
import random
import requests
import base64
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image

load_dotenv()


class ProductDocumentGenerator:
    """상품 문서 생성기"""

    def __init__(self):
        """OpenAI API 클라이언트 초기화"""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        self.client = OpenAI(api_key=api_key)
        self.model_name = "gpt-5-mini"

    def download_and_encode_image(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        이미지 다운로드 후 Base64 인코딩 (느린 서버 대응)

        Args:
            url: 이미지 URL
            timeout: 다운로드 타임아웃 (초)

        Returns:
            Base64 인코딩된 이미지 문자열 또는 None
        """
        try:
            # 이미지 다운로드 (긴 timeout 설정)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            # PIL로 이미지 처리
            img = Image.open(BytesIO(response.content))

            # RGB 변환
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 리사이즈 (너무 큰 이미지 방지)
            max_size = 2000
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Base64 인코딩
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            return img_base64

        except Exception as e:
            print(f"    [경고] 이미지 다운로드 실패 ({url}): {e}")
            return None

    def create_prompt(self, product: Dict) -> str:
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

        return prompt

    def analyze_product(self, product: Dict) -> Optional[str]:
        """
        상품 이미지를 분석하여 문서 생성 (1번만)

        하이브리드 방식:
        1. Direct URL 방식 시도 (빠름)
        2. timeout 에러 발생시 Base64 방식으로 폴백 (안정적)
        """
        image_urls = product.get('상품상세_이미지', [])

        if not image_urls:
            return None

        # 프롬프트 생성
        prompt = self.create_prompt(product)

        # 최대 3개 이미지만 사용
        selected_urls = image_urls[:3]

        try:
            # content 배열 생성
            content_list = [{"type": "text", "text": prompt}]

            # Direct URL 방식 (기본)
            for url in selected_urls:
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": url}
                })

            # API 호출 (gpt5-mini_test.py와 동일하게 파라미터 최소화)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": content_list
                }]
                # 파라미터 없음 (기본값 사용)
            )

            result_text = response.choices[0].message.content.strip()

            # 코드 블록 제거
            if "```" in result_text:
                result_text = result_text.split("```")[1].strip()
                if result_text.startswith("markdown") or result_text.startswith("text"):
                    result_text = "\n".join(result_text.split("\n")[1:])

            print(f"    문서 생성 완료")
            return result_text

        except Exception as e:
            error_msg = str(e)

            # timeout 에러 감지 - Base64로 재시도
            if "timeout" in error_msg.lower() or "invalid_image_url" in error_msg.lower():
                print(f"  [경고] URL timeout 감지 → Base64 방식으로 재시도")
                try:
                    # Base64 방식으로 재시도
                    content_list = [{"type": "text", "text": prompt}]

                    print(f"    [Base64 모드] 이미지 다운로드 중...")
                    for url in selected_urls:
                        img_base64 = self.download_and_encode_image(url)
                        if img_base64:
                            content_list.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                            })

                    if len(content_list) == 1:
                        print(f"    [에러] 모든 이미지 다운로드 실패")
                        return None

                    # Base64로 API 재호출
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{
                            "role": "user",
                            "content": content_list
                        }]
                    )

                    result_text = response.choices[0].message.content.strip()

                    if "```" in result_text:
                        result_text = result_text.split("```")[1].strip()
                        if result_text.startswith("markdown") or result_text.startswith("text"):
                            result_text = "\n".join(result_text.split("\n")[1:])

                    print(f"    [Base64] 문서 생성 완료")
                    return result_text

                except Exception as e2:
                    print(f"  [에러] Base64 방식도 실패: {e2}")
                    return None

            print(f"  [에러] 문서 생성 실패: {e}")
            return None

    def generate_document(self, product: Dict) -> Optional[Dict]:
        """상품 문서 생성 (JSONL 형식, 1개만)"""
        start_time = time.time()

        # 이미지 분석 (1번만)
        content = self.analyze_product(product)

        if not content:
            return None

        # 처리 시간
        processing_time = time.time() - start_time

        # 이미지 URL 섹션
        image_urls = product.get('상품상세_이미지', [])[:3]
        image_section = "사용 이미지 url\n"
        image_section += " ,\n".join(image_urls)
        image_section += "\n<<추출 예시>>\n\n"

        # 1개의 문서 생성
        full_content = image_section + content

        document = {
            "상품코드": product.get('url', '').split('=')[-1] if product.get('url') else '',
            "브랜드": product.get('브랜드', ''),
            "상품명": product.get('상품명', ''),
            "카테고리": product.get('tags', {}).get('category_tags', []),
            "문서내용": full_content,
            "메타데이터": {
                "생성일시": datetime.now().isoformat(),
                "모델": f"openai_{self.model_name}",
                "처리시간": round(processing_time, 2),
                "이미지개수": len(image_urls)
            }
        }

        return document


def process_products(
    input_file: str,
    output_file: str,
    max_products: int = 3,
    delay: float = 1.0,
    random_selection: bool = True
):
    """
    상품 배치 처리 (랜덤 선택 지원)

    Args:
        input_file: 입력 JSONL 파일
        output_file: 출력 JSONL 파일
        max_products: 처리할 상품 수 (기본 3개)
        delay: API 호출 간격 (초)
        random_selection: True면 랜덤 선택, False면 순차 선택
    """
    generator = ProductDocumentGenerator()
    total_docs = 0

    print("="*60)
    print("[상품 문서 생성 시작]")
    print(f"처리 상품 수: {max_products}개 (각 상품당 1개 문서)")
    print(f"선택 방식: {'랜덤 선택' if random_selection else '순차 선택'}")
    print(f"API 호출 간격: {delay}초")
    print(f"모델: {generator.model_name}")
    print("="*60 + "\n")

    # 입력 파일 읽기
    with open(input_file, 'r', encoding='utf-8') as f:
        products = [json.loads(line) for line in f if line.strip()]

    print(f"총 {len(products)}개 상품 로드 완료\n")

    # 상품 선택
    if random_selection:
        selected_products = random.sample(products, min(max_products, len(products)))
        print(f"[랜덤 선택] {max_products}개 상품을 무작위로 선택했습니다.")
        print("선택된 브랜드:", ", ".join(set(p.get('브랜드', '') for p in selected_products)))
        print()
    else:
        selected_products = products[:max_products]

    # 출력 파일 열기
    with open(output_file, 'w', encoding='utf-8') as f:
        # 처리
        for i, product in enumerate(selected_products, 1):
            brand = product.get('브랜드', '')
            product_name = product.get('상품명', '')
            product_code = product.get('url', '').split('=')[-1] if product.get('url') else f'unknown_{i}'

            print(f"[{i}/{max_products}] [{brand}] {product_name[:40]}...")

            document = generator.generate_document(product)

            if document:
                f.write(json.dumps(document, ensure_ascii=False) + '\n')
                total_docs += 1
                print(f"  [OK] 성공 (상품코드: {product_code})")
            else:
                print(f"  [FAIL] 실패")

            # Rate limiting
            if i < max_products:
                time.sleep(delay)

    print(f"\n{'='*60}")
    print(f"완료: {max_products}개 상품, 총 {total_docs}개 문서 생성")
    print(f"저장: {output_file}")
    print("="*60)


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    process_products(
        input_file=os.path.join(BASE_DIR, '../data/crawling_result/product_crawling_tagged.jsonl'),
        output_file=os.path.join(BASE_DIR, '../data/crawling_result/product_documents.jsonl'),
        max_products=3,  # 3개만 처리
        delay=1.0,
        random_selection=True  # 랜덤으로 다양한 브랜드 선택
    )
