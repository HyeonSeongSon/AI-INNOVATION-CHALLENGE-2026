import json
import os
from typing import Dict, Any

# OpenAI 클라이언트 설정
from openai import OpenAI

class PersonaAIService:
    def __init__(self):
        # API KEY는 환경변수에서 가져오거나 직접 입력
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("⚠️ 경고: OPENAI_API_KEY가 설정되지 않았습니다.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)

    # ✅ [추가] 리스트를 문자열로 예쁘게 변환하는 헬퍼 함수
    def _list_to_str(self, value):
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value) if value else "정보 없음"

    async def analyze_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [기능 2] 저장된 데이터를 불러와서:
        - Step 1~5: 키워드 형태로 매핑 (spec_keywords)
        - Step 6~7: 라이프스타일 문맥 형태로 정리 (lifestyle_context)
        """
        if not self.client:
            return self._get_dummy_analysis()

        # 1. 데이터 쪼개기 (헬퍼 함수 적용하여 리스트->문자열 변환)
        spec_data = {
            "name": data.get('name'),
            "age": data.get('age'),
            "gender": data.get('gender'),
            "skin_type": self._list_to_str(data.get('skin_type')),
            "concerns": self._list_to_str(data.get('concern_keywords')),
            "personal_color": data.get('personal_color'),
            "base_shade": data.get('base_shade'),
            "ingredients_pref": self._list_to_str(data.get('preferred_ingredients')),
            "ingredients_avoid": self._list_to_str(data.get('avoided_ingredients')),
            "values": self._list_to_str(data.get('values'))
        }

        life_data = {
            "routine": data.get('routine_type'),
            "environment": data.get('activity_environment'),
            "texture": self._list_to_str(data.get('preferred_texture')),
            "pet": data.get('pet_type'),
            "sleep": data.get('sleep_hours'),
            "stress": data.get('stress_level'),
            "digital": data.get('digital_device_hours'),
            "shopping": data.get('shopping_style'),
            "factor": self._list_to_str(data.get('purchase_factor'))
        }

        # 2. AI에게 분석 요청
        prompt = f"""
        너는 뷰티 데이터 분석가야. 아래 두 가지 데이터를 보고 지시대로 분석해줘.

        [DATA 1: 고객 스펙 (Step 1~5)]
        {json.dumps(spec_data, ensure_ascii=False)}

        [DATA 2: 라이프스타일 (Step 6~7)]
        {json.dumps(life_data, ensure_ascii=False)}

        [지시사항]
        1. 'keywords': [DATA 1]을 바탕으로 이 고객을 설명하는 핵심 키워드 5~7개를 리스트로 추출해. (예: #건성, #비건지향)
        2. 'lifestyle_summary': [DATA 2]를 바탕으로 이 사람의 하루와 생활 패턴을 3~4문장의 자연스러운 '문맥(Context)'으로 요약해. 
           (예: "주로 건조한 사무실에서 근무하며 스트레스가 높은 편입니다. 스킨케어는 간편한 것을 선호하지만...")
        3. 'primary_category': 피부 타입과 고민을 고려해 가장 필요한 제품 카테고리 1개를 영어 대문자로 적어. (예: MOISTURE, ANTI_AGING, TROUBLE)

        [출력 형식 (JSON)]
        {{
            "keywords": ["#키워드1", "#키워드2"],
            "lifestyle_summary": "문맥 요약 텍스트...",
            "primary_category": "CATEGORY"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",  # ✅ 요청하신 모델명 적용
                messages=[{"role": "system", "content": "You are a helpful beauty consultant."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            
            return {
                "tagging_keywords": result.get('keywords', []),
                "ai_analysis_text": result.get('lifestyle_summary', ""),
                "primary_category": result.get('primary_category', "MOISTURE")
            }
        except Exception as e:
            print(f"AI 분석 실패: {e}")
            return self._get_dummy_analysis()

    async def generate_solution(self, analysis_result: Dict, raw_data: Dict) -> Dict[str, Any]:
        """
        [기능 2-1] 분석된 결과를 바탕으로 초기 솔루션(처방) 생성
        """
        if not self.client:
            return {"detailed_solution": "API 키가 없습니다.", "vector_product_ids": []}

        context = analysis_result.get('ai_analysis_text', '')
        keywords = analysis_result.get('tagging_keywords', [])
        concerns = self._list_to_str(raw_data.get('concern_keywords')) # ✅ 리스트 -> 문자열
        
        prompt = f"""
        [고객 정보]
        - 키워드: {', '.join(keywords)}
        - 라이프스타일: {context}
        - 고민: {concerns}

        위 고객을 위한 맞춤형 뷰티 케어 가이드를 3문장 내외로 작성해줘.
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini", # ✅ 요청하신 모델명 적용
                messages=[{"role": "user", "content": prompt}]
            )
            return {
                "detailed_solution": response.choices[0].message.content,
                "vector_product_ids": [] 
            }
        except Exception as e:
            return {"detailed_solution": "솔루션 생성 실패", "vector_product_ids": []}

    async def recommend_product_type(self, analysis_result: Dict, raw_data: Dict, purpose: str, category: str, season: str) -> Dict[str, Any]:
        """
        [기능 3] 제품 유형 추천 가이드 (수정됨)
        - 페르소나 분석 결과 + 사용자 입력 조건(목적/카테고리/시즌)을 결합하여 추천
        """
        if not self.client:
            return {"detailed_solution": "API 키가 없습니다."}
        
        keywords = analysis_result.get('tagging_keywords', [])
        lifestyle = analysis_result.get('ai_analysis_text', '')
        texture = self._list_to_str(raw_data.get('preferred_texture'))
        
        # ✅ 프롬프트에 사용자 입력 조건 반영
        prompt = f"""
        [1. 고객 페르소나 정보]
        - 키워드: {', '.join(keywords)}
        - 라이프스타일: {lifestyle}
        - 선호 제형: {texture}

        [2. 요청 조건 (Context)]
        - 추천 목적: {purpose} (예: 신상품 추천, 선물, 트러블 케어 등)
        - 희망 카테고리: {category}
        - 현재 시즌(계절): {season}

        [3. AI 가이드 작성 요청]
        위 고객 페르소나와 요청 조건을 종합하여, 지금 당장 화장품 매장에서 **'어떤 스펙의 {category} 제품을 골라야 할지'** 명확한 기준을 제시해줘.
        
        [필수 포함 내용]
        1. 이상적인 제형 & 성분: "{season}" 계절과 "{lifestyle}" 라이프스타일을 고려할 때 적합한 제형과 성분 추천.
        2. 쇼핑 체크포인트: "{purpose}" 목적에 맞게 패키지나 라벨에서 확인해야 할 구체적인 문구 (예: 'Non-Comedogenic', '24H 보습').
        3. 추천 이유: 고객의 고민과 현재 요청 조건을 연결하여 설득력 있게 설명.

        [제약 사항]
        - 특정 브랜드 상품명(SKU)을 직접 언급하지 말고, '제품의 유형(Type)'을 묘사할 것.
        - 분량: 300자 이내로 핵심만 간결하게.
        - 말투: 전문적이지만 친절한 조언조 ("~한 제품을 선택하는 것이 좋습니다.")
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini", # 사용자 지정 모델
                messages=[{"role": "user", "content": prompt}]
            )
            return {"detailed_solution": response.choices[0].message.content}
        except Exception as e:
            return {"detailed_solution": "추천 가이드를 생성할 수 없습니다."}

    def _get_dummy_analysis(self):
        return {
            "tagging_keywords": ["#분석실패"],
            "ai_analysis_text": "AI 분석을 수행할 수 없습니다.",
            "primary_category": "ETC"
        }