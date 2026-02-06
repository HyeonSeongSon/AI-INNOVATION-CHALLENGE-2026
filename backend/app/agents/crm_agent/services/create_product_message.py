"""
상품 메시지 생성 Tool
선택된 상품, 페르소나 정보, 브랜드톤을 기반으로 목적별 맞춤 메시지 생성
"""

from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from pathlib import Path
from ..prompts.purpose_prompt import (build_purpose_bestseller_prompt, build_purpose_ingredient_efficacy_point_prompt, build_purpose_introduction_prompt, build_purpose_lifestyle_and_age_point_prompt, build_purpose_new_products_prompt, build_purpose_promotion_and_evnet_prompt, build_purpose_skintype_and_concern_point_prompt)
import os
import yaml
import requests

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


# ============================================================
# 메시지 생성 클래스
# ============================================================

class ProductMessageGenerator:
    def __init__(self):
        """메시지 생성기 초기화"""
        api_key = os.getenv("OPENAI_API_KEY")
        chat_gpt_model_name = os.getenv("CHATGPT_MODEL_NAME")
        self.vector_db_api_url = os.getenv("OPENSEARCH_API_URL")
        self.db_api_url = os.getenv("DATABASE_API_URL")

        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model=chat_gpt_model_name,
            temperature=0.7,
            api_key=api_key,
            request_timeout=30
        )

        # YAML 데이터 로드
        if os.environ.get("APP_ROOT"):
            ROOT_DIR = Path(os.environ.get("APP_ROOT"))
            DATA_PATH = ROOT_DIR / "agents" / "crm_agent" / "prompts" / "brand_tone.yaml"
            print(f"[INFO] os.environ 경로 사용")
        else:        
            ROOT_DIR = Path(__file__).resolve().parents[1]
            DATA_PATH = ROOT_DIR / "prompts" / "brand_tone.yaml"
            print(f'[INFO] Path(__file__) 경로 사용')
        
        self.brand_tones = self._load_yaml(DATA_PATH)

        print(f"[INFO] 메시지 생성기 초기화 완료")
        print(f"[INFO] 브랜드톤 데이터: {len(self.brand_tones.get('brand_ton_prompt', {}))}개 브랜드")

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
                f"{self.vector_db_api_url}/api/product/{product_id}",
                params={"index_name": "product_index"},
                timeout=10
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

        # 3. 페르소나 정보 포맷팅
        persona_text = self._format_persona_info(persona_info)

        # 4. 상품 정보 포맷팅
        product_text = self._format_product_info(product)

        # 5. 프롬프트 빌드
        PURPOSE_PROMPT_MAP = {
            "브랜드/제품 첫소개": build_purpose_introduction_prompt,
            "신제품 홍보": build_purpose_new_products_prompt,
            "베스트셀러 제품 소개": build_purpose_bestseller_prompt,
            "프로모션/이벤트 소개": build_purpose_promotion_and_evnet_prompt,
            "성분/효능 강조 소개": build_purpose_ingredient_efficacy_point_prompt,
            "피부타입/고민 강조 소개": build_purpose_skintype_and_concern_point_prompt,
            "라이프스타일/연령대 강조 소개": build_purpose_lifestyle_and_age_point_prompt
        }
        build_func = PURPOSE_PROMPT_MAP.get(purpose)
        prompt = build_func(brand_name, product.get('product_name'), product_text, product_document, brand_tone, persona_text)

        try:
            response = self.llm.invoke(prompt)
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