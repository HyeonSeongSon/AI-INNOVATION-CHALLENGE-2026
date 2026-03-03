import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from difflib import SequenceMatcher
import json
import os
import time

load_dotenv()

class PersonaTagger:
    """
    GPT-5-mini를 사용한 페르소나 기반 상품 태깅 시스템
    기존 상품 태그에 페르소나 정보를 추가
    """
    def __init__(self):
        """
        OpenAI API 클라이언트 초기화 및 카테고리 로드
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.client = OpenAI(api_key=api_key)
        self.persona_categories = self.load_persona_categories()
        self.products = self.load_products()

    def load_persona_categories(self) -> Dict:
        """페르소나 카테고리 파일 로드 (JSON)"""
        BASE_DIR = Path(__file__).parent.parent
        category_file = BASE_DIR / "data" / "comparison" / "persona_categories.json"

        print(f"페르소나 카테고리 파일 로드: {category_file}")

        if not category_file.exists():
            raise FileNotFoundError(f"페르소나 카테고리 파일을 찾을 수 없습니다: {category_file}")

        with open(category_file, 'r', encoding='utf-8') as f:
            categories = json.load(f)

        print(f"페르소나 카테고리 로드 완료\n")
        return categories

    def load_products(self) -> List[Dict]:
        """태깅된 상품 문서 로드 (product_documents_tagged.jsonl)"""
        BASE_DIR = Path(__file__).parent.parent
        input_file = BASE_DIR / "data" / "crawling_result" / "product_documents_tagged copy.jsonl"

        print(f"상품 파일 로드: {input_file}")

        if not input_file.exists():
            raise FileNotFoundError(f"상품 파일을 찾을 수 없습니다: {input_file}")

        products = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    products.append(json.loads(line))

        print(f"총 {len(products)}개 상품 로드 완료\n")
        return products

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """
        두 문자열 간의 유사도 계산 (0.0 ~ 1.0)
        """
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def find_best_match(self, tag: str, category_list: List[str], threshold: float = 0.6) -> Tuple[str, float]:
        """
        GPT 출력 태그와 가장 유사한 카테고리 찾기

        Args:
            tag: GPT가 반환한 태그
            category_list: 비교할 카테고리 리스트
            threshold: 최소 유사도 임계값

        Returns:
            (매칭된 카테고리, 유사도) 튜플
        """
        best_match = None
        best_score = 0.0

        for category in category_list:
            score = self.calculate_similarity(tag, category)
            if score > best_score:
                best_score = score
                best_match = category

        # 임계값 이상인 경우에만 반환
        if best_score >= threshold:
            return best_match, best_score
        else:
            return tag, best_score  # 원본 반환

    def validate_persona_tags(self, persona_tags: Dict) -> Tuple[Dict, List[str]]:
        """
        페르소나 태그 검증 및 보정

        Args:
            persona_tags: GPT가 반환한 페르소나 태그

        Returns:
            (보정된 태그, 보정 로그 리스트)
        """
        corrected_tags = {}
        correction_logs = []

        # 각 카테고리별로 검증
        category_mapping = {
            'skin_type': self.persona_categories['skin_spec']['피부타입'],
            'personal_color': self.persona_categories['skin_spec']['퍼스널컬러'],
            'base_shade': self.persona_categories['skin_spec']['베이스호수'],
            'skin_concerns': self.persona_categories['skin_concerns']['고민키워드'],
            'preferred_colors': self.persona_categories['makeup_preference']['선호포인트컬러'],
            'positive_ingredients': self.persona_categories['ingredient_preference']['선호성분'],
            'negative_ingredients_free': self.persona_categories['ingredient_preference']['기피성분'],
            'scent': self.persona_categories['ingredient_preference']['선호향'],
            'special_conditions': self.persona_categories['values']['특수조건']
        }

        for key, valid_categories in category_mapping.items():
            if key not in persona_tags:
                corrected_tags[key] = []
                continue

            tags = persona_tags[key]
            if not isinstance(tags, list):
                tags = [tags]

            corrected_list = []
            for tag in tags:
                if not isinstance(tag, str):
                    tag = str(tag)

                # 정확히 일치하는 경우
                if tag in valid_categories:
                    corrected_list.append(tag)
                else:
                    # 유사도 매칭
                    matched_category, score = self.find_best_match(tag, valid_categories, threshold=0.6)

                    if matched_category != tag:
                        corrected_list.append(matched_category)
                        correction_logs.append(f"[{key}] '{tag}' → '{matched_category}' (유사도: {score:.2f})")
                    else:
                        # 매칭 실패
                        if score > 0.4:  # 낮은 유사도라도 기록
                            corrected_list.append(matched_category)
                            correction_logs.append(f"[{key}] '{tag}' → '{matched_category}' (낮은 유사도: {score:.2f})")
                        else:
                            correction_logs.append(f"[{key}] '{tag}' → 제외 (매칭 실패)")

            corrected_tags[key] = corrected_list

        return corrected_tags, correction_logs

    def create_persona_prompt(self, product: Dict) -> str:
        """
        페르소나 태깅을 위한 GPT 프롬프트 생성

        Args:
            product: 상품 정보 (브랜드, 상품명, 카테고리, 생성된_문서 포함)

        Returns:
            GPT 프롬프트 문자열
        """
        brand = product.get('브랜드', '')
        product_name = product.get('상품명', '')
        category = product.get('태그', '')
        product_doc = product.get('생성된_문서', '')

        # 페르소나 카테고리를 JSON으로 변환
        categories_json = json.dumps(self.persona_categories, ensure_ascii=False, indent=2)

        prompt = f"""당신은 화장품 전문가입니다. 상품 정보를 분석하여 이 제품에 적합한 고객 특성을 태그로 분류하세요.

[상품 정보]
브랜드: {brand}
상품명: {product_name}
카테고리: {category}

[상품 문서]
{product_doc[:3000]}

[분류 가능한 페르소나 카테고리]
{categories_json}

[분석 지침]

1. **피부타입** (skin_type)
   - 상품 문서에서 타겟 고민, 제형 특성 분석
   - 보습 중심 → 건성/악건성, 피지 조절 → 지성/복합성, 진정 → 민감성/트러블성
   - 해당하는 모든 타입 선택 (복수 가능)

2. **퍼스널컬러** (personal_color)
   - 색조 제품(립/아이섀도우/블러셔 등)만 분석
   - 색상명에서 톤 판단: 코랄/피치/오렌지→웜톤, 핑크/로즈/베리→쿨톤
   - 색조 아니면 빈 배열

3. **베이스호수** (base_shade)
   - 베이스 메이크업(파운데이션/쿠션/컨실러/BB/CC)만 분석
   - 호수 정보 추출: "21호", "21N", "밝은 베이지" 등
   - 베이스 아니면 빈 배열

4. **고민키워드** (skin_concerns)
   - "소구 포인트" 섹션 중심 분석
   - 해결하는 피부 고민 모두 선택 (잡티/미백/주름/각질/여드름/블랙헤드/피지과다/아토피/민감성/다크서클/기미/홍조/유수분밸런스/탄력/트러블자국/비듬/탈모)
   - 해당하는 모든 키워드 추출

5. **선호포인트컬러** (preferred_colors)
   - 색조 제품의 주요 컬러 계열 분석
   - 레드/핑크/코랄/오렌지/베이지/브라운 중 선택
   - 색조 아니면 빈 배열

6. **선호성분** (positive_ingredients)
   - "성분 스토리" 섹션에서 핵심 성분 확인
   - 리스트의 성분명 또는 유사 표기 매칭 (히알루론산/나이아신아마이드/레티놀/비타민C/펩타이드/시카/티트리/세라마이드/콜라겐/알부틴)
   - 명시된 성분만 선택

7. **기피성분** (negative_ingredients_free)
   - "무첨가", "프리", "Free" 명시적 표기만 인정
   - 예: "파라벤 프리", "무알코올"
   - 추측하지 말고 명시된 것만

8. **선호향** (scent)
   - "감각/제형" 섹션 향 정보 확인
   - 무향/플로럴/시트러스/허브/우디/머스크
   - 무향 우선, 없으면 빈 배열

9. **특수조건** (special_conditions)
   - 인증 마크, 특수 표기 확인
   - 천연/유기농, 비건/크루얼티프리, 친환경패키징, 임산부/수유부
   - 명시된 것만

[출력 형식]
JSON만 출력, 다른 설명 없이:

{{
  "skin_type": [],
  "personal_color": [],
  "base_shade": [],
  "skin_concerns": [],
  "preferred_colors": [],
  "positive_ingredients": [],
  "negative_ingredients_free": [],
  "scent": [],
  "special_conditions": []
}}

**중요:**
- 해당 사항 없으면 빈 배열 []
- 카테고리 리스트의 값만 사용
- 해당되는 모든 항목 포함 (복수 선택 가능)
- 명시적 정보만, 추측 금지

출력:"""

        return prompt

    def tag_product_persona(self, product: Dict) -> Tuple[Dict, str]:
        """
        GPT-5-mini를 사용하여 상품에 페르소나 태그 추가

        Args:
            product: 상품 정보

        Returns:
            (페르소나 태그 딕셔너리, 에러 로그)
        """
        prompt = self.create_persona_prompt(product)

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            result = response.choices[0].message.content.strip()

            # JSON 파싱
            # ```json ``` 마크다운 제거
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

            # JSON 파싱
            try:
                persona_tags = json.loads(result)

                # 기본 구조 검증
                required_keys = [
                    "skin_type", "personal_color", "base_shade",
                    "skin_concerns", "preferred_colors", "positive_ingredients",
                    "negative_ingredients_free", "scent", "special_conditions"
                ]

                for key in required_keys:
                    if key not in persona_tags:
                        persona_tags[key] = []

                # 유사도 검증 및 보정
                corrected_tags, correction_logs = self.validate_persona_tags(persona_tags)

                # 보정 로그가 있으면 반환
                if correction_logs:
                    log_message = " | ".join(correction_logs[:3])  # 최대 3개만
                    return corrected_tags, log_message
                else:
                    return corrected_tags, ""

            except json.JSONDecodeError as e:
                return {
                    "skin_type": [], "personal_color": [], "base_shade": [],
                    "skin_concerns": [], "preferred_colors": [], "positive_ingredients": [],
                    "negative_ingredients_free": [], "scent": [], "special_conditions": []
                }, f"JSON 파싱 에러: {str(e)}"

        except Exception as e:
            print(f"  [경고] 페르소나 태깅 실패: {e}")
            return {
                "skin_type": [], "personal_color": [], "base_shade": [],
                "skin_concerns": [], "preferred_colors": [], "positive_ingredients": [],
                "negative_ingredients_free": [], "scent": [], "special_conditions": []
            }, f"API 에러: {str(e)}"

    def process_all(self):
        """모든 상품 처리"""
        results = []
        start_time = datetime.now()

        print("=" * 60)
        print("페르소나 태깅 시작")
        print("=" * 60)
        print(f"처리 상품 수: {len(self.products)}개")
        print(f"모델: gpt-5-mini")
        print(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()

        for idx, product in enumerate(self.products, 1):
            try:
                brand = product.get('브랜드', '')
                product_name = product.get('상품명', '')
                category = product.get('태그', '')

                print(f"[{idx}/{len(self.products)}] {brand} - {product_name[:40]}{'...' if len(product_name) > 40 else ''}")
                print(f"  카테고리: {category}")

                # 페르소나 태그 생성
                persona_tags, error_log = self.tag_product_persona(product)

                if error_log:
                    print(f"  ⚠ {error_log}")

                # 기존 정보에 카테고리태그 추가
                result = {
                    '브랜드': brand,
                    '상품명': product_name,
                    '생성된_문서': product.get('생성된_문서', ''),
                    '태그': category,
                    '카테고리태그': persona_tags
                }
                results.append(result)

                # 태그 요약 출력
                tag_summary = []
                if persona_tags.get('skin_type'):
                    tag_summary.append(f"피부: {', '.join(persona_tags['skin_type'])}")
                if persona_tags.get('skin_concerns'):
                    tag_summary.append(f"고민: {', '.join(persona_tags['skin_concerns'][:3])}")
                if persona_tags.get('positive_ingredients'):
                    tag_summary.append(f"성분: {', '.join(persona_tags['positive_ingredients'][:3])}")

                if tag_summary:
                    print(f"  ✓ {' | '.join(tag_summary)}")
                else:
                    print(f"  ✓ 기본 정보만 적용")
                print()

                # API 호출 제한 방지
                time.sleep(0.5)

            except Exception as e:
                print(f"  [ERROR] 실패: {str(e)}\n")
                # 실패해도 기본 구조는 유지
                result = {
                    '브랜드': product.get('브랜드', ''),
                    '상품명': product.get('상품명', ''),
                    '생성된_문서': product.get('생성된_문서', ''),
                    '태그': product.get('태그', ''),
                    '카테고리태그': {
                        "skin_type": [], "personal_color": [], "base_shade": [],
                        "skin_concerns": [], "preferred_colors": [], "positive_ingredients": [],
                        "negative_ingredients_free": [], "scent": [], "special_conditions": []
                    }
                }
                results.append(result)

        # 결과 저장
        self.save_results(results, start_time)

        return results

    def save_results(self, results: List[Dict], start_time: datetime):
        """결과를 JSONL 파일로 저장"""
        BASE_DIR = Path(__file__).parent.parent
        output_path = BASE_DIR / "data" / "crawling_result" / "product_documents_with_persona.jsonl"

        print("=" * 60)
        print("결과 저장 중...")
        print("=" * 60)

        with open(output_path, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        end_time = datetime.now()
        elapsed = end_time - start_time

        print(f"✓ 총 {len(results)}개의 상품에 페르소나 태그가 추가되었습니다.")
        print(f"  저장 경로: {output_path}")
        print(f"  소요 시간: {elapsed}")
        print("=" * 60)

if __name__ == "__main__":
    tagger = PersonaTagger()
    tagger.process_all()
