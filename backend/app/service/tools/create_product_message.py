"""
상품 메시지 생성 Tool
선택된 상품, 페르소나 정보, 브랜드톤을 기반으로 목적별 맞춤 메시지 생성
"""

from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import yaml
import requests
import json as json_module

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


# ============================================================
# 메시지 생성 클래스
# ============================================================

class ProductMessageGenerator:
    def __init__(self):
        """메시지 생성기 초기화"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-5-mini",
            temperature=1,
            api_key=api_key
        )

        # YAML 파일 경로 설정
        # __file__의 위치: backend/app/service/tools/create_product_message.py
        # 프로젝트 루트: AI-INNOVATION-CHALLENGE-2026/
        current_dir = os.path.dirname(os.path.abspath(__file__))  # tools/
        service_dir = os.path.dirname(current_dir)  # service/
        app_dir = os.path.dirname(service_dir)  # app/
        backend_dir = os.path.dirname(app_dir)  # backend/
        project_root = os.path.dirname(backend_dir)  # AI-INNOVATION-CHALLENGE-2026/

        self.brand_tone_path = os.path.join(project_root, "data", "prompt", "brand_tone.yaml")
        self.purpose_prompt_path = os.path.join(project_root, "data", "prompt", "purpose_prompt.yaml")

        # YAML 데이터 로드
        self.brand_tones = self._load_yaml(self.brand_tone_path)
        self.purpose_prompts = self._load_yaml(self.purpose_prompt_path)

        print(f"[INFO] 메시지 생성기 초기화 완료")
        print(f"[INFO] 브랜드톤 데이터: {len(self.brand_tones.get('brand_ton_prompt', {}))}개 브랜드")
        print(f"[INFO] 목적별 프롬프트: {len(self.purpose_prompts.get('MESSAGE_PURPOSE_PROMPT', {}))}개 목적")

    def _load_yaml(self, file_path: str) -> Dict[str, Any]:
        """YAML 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data
        except Exception as e:
            print(f"[ERROR] YAML 파일 로드 실패: {file_path}")
            print(f"[ERROR] {e}")
            return {}

    def _get_product_document(self, product_id: str) -> Optional[str]:
        """
        오픈서치에서 product_id로 상품 문서 내용만 조회

        Args:
            product_id: 조회할 상품 ID

        Returns:
            상품 문서 내용 (텍스트) 또는 None
        """
        try:
            # 오픈서치 API 호출 (GET 방식으로 단일 product_id 조회)
            response = requests.get(
                f"http://host.docker.internal:8010/api/product/{product_id}",
                params={"index_name": "product_index"}
            )
            response.raise_for_status()
            api_response = response.json()

            # 결과 파싱 - 문서 필드만 추출
            if api_response.get("success") and "document" in api_response:
                document = api_response["document"]
                # '문서' 필드만 반환
                document_text = document.get("문서", "")
                if document_text:
                    print(f"[INFO] 상품 문서 조회 성공: {product_id}")
                    return document_text
                else:
                    print(f"[WARNING] 상품 문서에 '문서' 필드가 없음: {product_id}")
                    return None
            else:
                print(f"[WARNING] 상품 문서를 찾을 수 없음: {product_id}")
                return None

        except Exception as e:
            print(f"[ERROR] 상품 문서 조회 실패: {e}")
            return None

    def _get_brand_tone(self, brand_name: str) -> str:
        """브랜드톤 가져오기"""
        brand_tones = self.brand_tones.get('brand_ton_prompt', {})

        # 정확한 브랜드명으로 검색
        if brand_name in brand_tones:
            return brand_tones[brand_name]

        # 대소문자 무시하고 검색
        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

        # 브랜드톤이 없으면 기본 톤 반환
        print(f"[WARNING] '{brand_name}' 브랜드톤을 찾을 수 없습니다. 기본 톤 사용")
        return "친근하면서도 전문적이고 신뢰감 있는 어조"

    def _get_purpose_prompt(self, purpose: str) -> str:
        """목적별 프롬프트 가져오기"""
        purpose_prompts = self.purpose_prompts.get('MESSAGE_PURPOSE_PROMPT', {})

        # 목적 매핑 (한글 -> 영문 키)
        purpose_mapping = {
            "브랜드/제품 첫소개": "INTRODUCTION_PROMPT",
            "신제품 홍보": "NEW_PRODUCTS_PROMPT",
            "베스트셀러 제품 소개": "BESTSELLER_PROMPT",
            "프로모션/이벤트 소개": "PROMOTION_AND_EVENT",
            "성분/효능 강조 소개": "INGREDIENT_EFFICACY_POINT_PROMPT",
            "피부타입/고민 강조 소개": "SKINTYPE_AND_CONCERN_POINT_PROMPT",
            "라이프스타일/연령대 강조 소개": "LIFESTYLE_AND_AGE_POINT_PROMPT"
        }

        # 매핑된 키로 검색
        prompt_key = purpose_mapping.get(purpose)
        if prompt_key and prompt_key in purpose_prompts:
            return purpose_prompts[prompt_key]

        # 직접 키로 검색
        if purpose in purpose_prompts:
            return purpose_prompts[purpose]

        # 기본값: INTRODUCTION_PROMPT 사용
        print(f"[WARNING] '{purpose}' 목적 프롬프트를 찾을 수 없습니다. INTRODUCTION_PROMPT 사용")
        return purpose_prompts.get("INTRODUCTION_PROMPT", "")

    def _format_persona_info(self, persona_info: Dict[str, Any]) -> str:
        """페르소나 정보를 텍스트로 포맷팅"""
        sections = []

        # 기본 정보
        if persona_info.get('이름'):
            sections.append(f"이름: {persona_info['이름']}")
        if persona_info.get('나이'):
            sections.append(f"나이: {persona_info['나이']}세")
        if persona_info.get('성별'):
            sections.append(f"성별: {persona_info['성별']}")

        # 피부 정보
        if persona_info.get('피부타입'):
            skin_type = persona_info['피부타입']
            if isinstance(skin_type, list):
                sections.append(f"피부타입: {', '.join(skin_type)}")
            else:
                sections.append(f"피부타입: {skin_type}")

        if persona_info.get('고민 키워드'):
            concerns = persona_info['고민 키워드']
            if isinstance(concerns, list):
                sections.append(f"피부 고민: {', '.join(concerns)}")
            else:
                sections.append(f"피부 고민: {concerns}")

        # 뷰티 정보
        if persona_info.get('퍼스널 컬러'):
            sections.append(f"퍼스널 컬러: {persona_info['퍼스널 컬러']}")

        if persona_info.get('선호 성분'):
            ingredients = persona_info['선호 성분']
            if isinstance(ingredients, list):
                sections.append(f"선호 성분: {', '.join(ingredients)}")
            else:
                sections.append(f"선호 성분: {ingredients}")

        if persona_info.get('기피 성분'):
            avoided = persona_info['기피 성분']
            if isinstance(avoided, list):
                sections.append(f"기피 성분: {', '.join(avoided)}")
            else:
                sections.append(f"기피 성분: {avoided}")

        # 가치관
        if persona_info.get('가치관'):
            values = persona_info['가치관']
            if isinstance(values, list):
                sections.append(f"가치관: {', '.join(values)}")
            else:
                sections.append(f"가치관: {values}")

        # 라이프스타일
        if persona_info.get('직업') or persona_info.get('occupation'):
            occupation = persona_info.get('직업') or persona_info.get('occupation')
            sections.append(f"직업: {occupation}")

        if persona_info.get('주 활동 환경') or persona_info.get('main_environment'):
            env = persona_info.get('주 활동 환경') or persona_info.get('main_environment')
            sections.append(f"주 활동 환경: {env}")

        if persona_info.get('쇼핑 스타일&예산') or persona_info.get('shopping_style'):
            shopping = persona_info.get('쇼핑 스타일&예산') or persona_info.get('shopping_style')
            sections.append(f"쇼핑 스타일: {shopping}")

        if persona_info.get('구매 결정 요인') or persona_info.get('purchase_decision_factors'):
            factors = persona_info.get('구매 결정 요인') or persona_info.get('purchase_decision_factors')
            if isinstance(factors, list) and factors:
                sections.append(f"구매 결정 요인: {', '.join(factors)}")
            elif factors:
                sections.append(f"구매 결정 요인: {factors}")

        if persona_info.get('스킨케어 루틴') or persona_info.get('skincare_routine'):
            routine = persona_info.get('스킨케어 루틴') or persona_info.get('skincare_routine')
            sections.append(f"스킨케어 루틴: {routine}")

        if persona_info.get('선호 제형') or persona_info.get('preferred_texture'):
            texture = persona_info.get('선호 제형') or persona_info.get('preferred_texture')
            if isinstance(texture, list) and texture:
                sections.append(f"선호 제형: {', '.join(texture)}")
            elif texture:
                sections.append(f"선호 제형: {texture}")

        if persona_info.get('선호 향') or persona_info.get('preferred_scents'):
            scents = persona_info.get('선호 향') or persona_info.get('preferred_scents')
            if isinstance(scents, list) and scents:
                sections.append(f"선호 향: {', '.join(scents)}")
            elif scents:
                sections.append(f"선호 향: {scents}")

        if persona_info.get('선호 색상') or persona_info.get('preferred_colors'):
            colors = persona_info.get('선호 색상') or persona_info.get('preferred_colors')
            if isinstance(colors, list) and colors:
                sections.append(f"선호 색상: {', '.join(colors)}")
            elif colors:
                sections.append(f"선호 색상: {colors}")

        if persona_info.get('반려동물') or persona_info.get('pets'):
            pets = persona_info.get('반려동물') or persona_info.get('pets')
            sections.append(f"반려동물: {pets}")

        if persona_info.get('평균 수면시간') or persona_info.get('avg_sleep_hours'):
            sleep = persona_info.get('평균 수면시간') or persona_info.get('avg_sleep_hours')
            sections.append(f"평균 수면시간: {sleep}시간")

        if persona_info.get('스트레스 수준') or persona_info.get('stress_level'):
            stress = persona_info.get('스트레스 수준') or persona_info.get('stress_level')
            sections.append(f"스트레스 수준: {stress}")

        if persona_info.get('디지털 기기 사용시간') or persona_info.get('digital_device_usage_time'):
            device_time = persona_info.get('디지털 기기 사용시간') or persona_info.get('digital_device_usage_time')
            sections.append(f"디지털 기기 사용시간: {device_time}시간")

        return "\n".join(sections)

    def _format_product_info(self, product: Dict[str, Any]) -> str:
        """상품 정보를 텍스트로 포맷팅"""
        sections = []

        # 기본 정보
        if product.get('product_name'):
            sections.append(f"{product['product_name']}")

        if product.get('brand'):
            sections.append(f"브랜드: {product['brand']}")

        if product.get('product_tag'):
            sections.append(f"카테고리: {product['product_tag']}")

        # 가격 정보
        if product.get('sale_price'):
            price_text = f"가격: {product['sale_price']:,}원"
            if product.get('discount_rate') and product['discount_rate'] > 0:
                price_text += f" ({product['discount_rate']}% 할인)"
            sections.append(price_text)

        # 평점 정보
        if product.get('rating'):
            rating_text = f"평점: {product['rating']}"
            if product.get('review_count'):
                rating_text += f" (리뷰 {product['review_count']}개)"
            sections.append(rating_text)

        # 상품 특성
        if product.get('skin_type'):
            skin_types = product['skin_type']
            if isinstance(skin_types, list) and skin_types:
                sections.append(f"적합 피부타입: {', '.join(skin_types)}")

        if product.get('skin_concerns'):
            concerns = product['skin_concerns']
            if isinstance(concerns, list) and concerns:
                sections.append(f"타겟 고민: {', '.join(concerns)}")

        if product.get('preferred_ingredients'):
            ingredients = product['preferred_ingredients']
            if isinstance(ingredients, list) and ingredients:
                sections.append(f"주요 성분: {', '.join(ingredients)}")

        if product.get('preferred_colors'):
            colors = product['preferred_colors']
            if isinstance(colors, list) and colors:
                sections.append(f"선호 색상: {', '.join(colors)}")

        if product.get('values'):
            values = product['values']
            if isinstance(values, list) and values:
                sections.append(f"브랜드 가치: {', '.join(values)}")

        # URL
        if product.get('product_page_url'):
            sections.append(f"상품 페이지: {product['product_page_url']}")

        return "\n".join(sections)

    def generate_message(
        self,
        product: Dict[str, Any],
        persona_info: Dict[str, Any],
        purpose: str = "브랜드/제품 소개"
    ) -> Dict[str, Any]:
        """
        상품 메시지 생성

        Args:
            product: 선택된 상품 정보
            persona_info: 페르소나 정보
            purpose: 메시지 목적 (예: "브랜드/제품 소개", "신상품홍보")

        Returns:
            생성된 메시지 딕셔너리
        """
        print(f"\n[INFO] 메시지 생성 시작")
        print(f"[INFO] 목적: {purpose}")
        print(f"[INFO] 상품: {product.get('product_name', 'N/A')}")
        print(f"[INFO] 브랜드: {product.get('brand', 'N/A')}")

        # 1. product_id로 상품 문서 가져오기
        product_id = product.get('product_id')
        product_document = None
        if product_id:
            print(f"[INFO] product_id로 상품 문서 조회 중: {product_id}")
            product_document = self._get_product_document(product_id)
        else:
            print(f"[WARNING] product_id가 없어 상품 문서를 가져올 수 없습니다.")

        # 2. 브랜드톤 가져오기
        brand_name = product.get('brand', '')
        brand_tone = self._get_brand_tone(brand_name)

        # 3. 목적별 프롬프트 가져오기
        purpose_prompt = self._get_purpose_prompt(purpose)

        if not purpose_prompt:
            return {
                "success": False,
                "error": f"목적 '{purpose}'에 해당하는 프롬프트를 찾을 수 없습니다."
            }

        # 4. 페르소나 정보 포맷팅
        persona_text = self._format_persona_info(persona_info)

        # 5. 상품 정보 포맷팅
        product_text = self._format_product_info(product)

        # 6. 프롬프트 변수 치환
        formatted_prompt = purpose_prompt.format(
            brand_name=brand_name,
            product_name=product.get('product_name', ''),
            product_text=product_text,
            brand_tone=brand_tone,
            persona_text=persona_text if persona_text else "정보 없음",
            product_document=product_document if product_document else "추가 문서 정보 없음"
        )

        print(f"\n[DEBUG] 생성 프롬프트")
        print("=" * 80)
        print(formatted_prompt)
        print("=" * 80)

        # 7. LLM 호출
        try:
            response = self.llm.invoke(formatted_prompt)
            message_content = response.content

            print(f"\n[INFO] 메시지 생성 완료")

            # 8. 결과 파싱 (제목/메시지 분리)
            result = self._parse_message(message_content)
            result['success'] = True
            result['full_content'] = message_content
            result['product_name'] = product.get('product_name', '')
            result['brand'] = brand_name
            result['purpose'] = purpose

            return result

        except Exception as e:
            print(f"[ERROR] LLM 호출 실패: {e}")
            return {
                "success": False,
                "error": f"메시지 생성 중 오류 발생: {str(e)}"
            }

    def _parse_message(self, content: str) -> Dict[str, str]:
        """
        생성된 메시지에서 제목과 본문 파싱

        출력 형식:
        제목: [제목 내용]
        메시지: [메시지 본문]
        """
        lines = content.strip().split('\n')
        result = {
            "title": "",
            "message": ""
        }

        current_section = None
        message_lines = []

        for line in lines:
            line = line.strip()

            if line.startswith("제목:"):
                result["title"] = line.replace("제목:", "").strip()
                current_section = "title"
            elif line.startswith("메시지:"):
                result["message"] = line.replace("메시지:", "").strip()
                current_section = "message"
                message_lines = [result["message"]] if result["message"] else []
            elif current_section == "message" and line:
                message_lines.append(line)

        # 메시지 본문이 여러 줄인 경우 합치기
        if message_lines:
            result["message"] = "\n".join(message_lines)

        return result


# ============================================================
# Tool 래핑
# ============================================================

# 전역 인스턴스 (싱글톤)
_message_generator = None

def _get_message_generator():
    """메시지 생성기 인스턴스 가져오기"""
    global _message_generator
    if _message_generator is None:
        _message_generator = ProductMessageGenerator()
    return _message_generator


@tool
def create_product_message(
    product: Dict[str, Any],
    persona_info: Dict[str, Any],
    purpose: str = "브랜드/제품 첫소개"
) -> Dict[str, Any]:
    """
    선택된 상품과 페르소나 정보를 바탕으로 개인화된 CRM 메시지를 생성합니다.

    **언제 사용하나요?**
    - 사용자가 특정 상품을 선택한 후 (recommend_products의 결과로 selected_product를 받은 후)
    - 페르소나 정보와 상품 정보가 모두 있을 때
    - 최종 CRM 메시지를 생성해야 할 때

    **필수 입력:**
    - product: 선택된 상품 정보 (recommend_products에서 반환한 selected_product)
      - product_id 필드 필수 (상품 문서 조회에 사용됨)
    - persona_info: 페르소나 정보 (parse_crm_message_request에서 반환한 persona_info)
    - purpose: 메시지 목적 - **반드시 다음 7개 중 정확히 하나를 사용하세요**
      - "브랜드/제품 첫소개" (기본값)
      - "신제품 홍보"
      - "베스트셀러 제품 소개"
      - "프로모션/이벤트 소개"
      - "성분/효능 강조 소개"
      - "피부타입/고민 강조 소개"
      - "라이프스타일/연령대 강조 소개"

    **중요: purpose 값 주의사항**
    - purpose 파라미터는 parse_crm_message_request에서 반환된 값을 **그대로** 사용해야 합니다
    - 절대로 임의로 값을 변형하거나 추가 텍스트를 붙이지 마세요
    - 예시) "신제품 홍보 - 라이프스타일 강조" (❌ 잘못됨)
    - 예시) "신제품 홍보" (✅ 올바름)

    **자동 처리:**
    - product_id를 사용하여 오픈서치에서 상품의 상세 문서를 자동으로 조회합니다

    Args:
        product: 선택된 상품 정보 딕셔너리
            - product_id: 상품 ID (필수)
            - product_name: 상품명
            - brand: 브랜드명
            - sale_price: 판매가
            - 기타 상품 속성
        persona_info: 페르소나 정보 딕셔너리
            - 이름, 나이, 성별
            - 피부타입, 고민 키워드
            - 선호 성분, 가치관 등
        purpose: 메시지 목적 (기본값: "브랜드/제품 첫소개")

    Returns:
        생성된 메시지:
        {
            "success": true,
            "title": "메시지 제목 (40자 이내)",
            "message": "메시지 본문 (350자 이내)",
            "product_name": "상품명",
            "brand": "브랜드명"
        }
    """
    generator = _get_message_generator()
    return generator.generate_message(product, persona_info, purpose)


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    import sys
    import io

    # Windows 콘솔 UTF-8 인코딩 설정
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("=== 상품 메시지 생성 테스트 ===\n")

    # 테스트 상품 정보
    test_product = {
        "product_id": "TEST001",
        "product_name": "[NEW 컬러 출시]센슈얼 틴티드 샤인스틱 3.5g",
        "brand": "헤라",
        "product_tag": "립스틱&틴트",
        "sale_price": 35000,
        "discount_rate": 10,
        "rating": 4.8,
        "review_count": 1250,
        "skin_type": ["건성", "복합성"],
        "skin_concerns": ["건조함", "칙칙함"],
        "preferred_ingredients": ["히알루론산", "나이아신아마이드"],
        "values": ["비건", "친환경"],
        "product_page_url": "https://www.amoremall.com/test"
    }

    # 테스트 페르소나 정보
    test_persona = {
        "persona_id": "PERSONA_002",
        "이름": "김소현",
        "나이": 23,
        "성별": "여성",
        "피부타입": ["건조함", "트러블성"],
        "고민 키워드": ["수분부족", "탄력저하"],
        "퍼스널 컬러": "쿨톤",
        "선호 성분": ["히알루론산", "나이아신아마이드"],
        "기피 성분": ["알코올", "파라벤"],
        "가치관": ["비건", "친환경"],
        "주 활동 환경": "실내",
        "쇼핑 스타일&예산": "가성비"
    }

    # 메시지 생성
    result = create_product_message.invoke({
        "product": test_product,
        "persona_info": test_persona,
        "purpose": "신상품홍보"
    })

    # 결과 출력
    print("\n" + "=" * 80)
    print("[생성 결과]")
    print("=" * 80)

    if result.get("success"):
        print(f"\n제목: {result.get('title', 'N/A')}")
        print(f"\n메시지:\n{result.get('message', 'N/A')}")
        print(f"\n상품: {result.get('product_name', 'N/A')}")
        print(f"브랜드: {result.get('brand', 'N/A')}")
        print(f"목적: {result.get('purpose', 'N/A')}")
    else:
        print(f"\n[오류] {result.get('error', '알 수 없는 오류')}")