import json
import os
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

class PersonaAIService:
    def __init__(self):
        # API KEY 확인
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("⚠️ 경고: OPENAI_API_KEY가 설정되지 않았습니다.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)

    def _list_to_str(self, value):
        """리스트면 콤마 문자열로, 아니면 그대로 반환"""
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value) if value else "정보 없음"

    async def analyze_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [기능] 페르소나 데이터 분석
        """
        if not self.client:
            return self._get_dummy_analysis()

        # 1. 프롬프트용 데이터 정리
        spec_data = {
            "name": data.get('name'),
            "age": data.get('age'),
            "gender": data.get('gender'),
            "skin_type": self._list_to_str(data.get('skin_type')),
            "concerns": self._list_to_str(data.get('skin_concerns')), # Pydantic 모델 필드명 주의
            "personal_color": data.get('personal_color'),
            "ingredients_pref": self._list_to_str(data.get('preferred_ingredients')),
            "values": self._list_to_str(data.get('values'))
        }

        life_data = {
            "routine": data.get('skincare_routine'),
            "environment": data.get('main_environment'),
            "texture": self._list_to_str(data.get('preferred_texture')),
            "sleep": data.get('avg_sleep_hours'),
            "stress": data.get('stress_level'),
            "factor": self._list_to_str(data.get('purchase_decision_factors'))
        }

        # 2. AI 요청 프롬프트
        prompt = f"""
        너는 뷰티 데이터 분석가야. 아래 데이터를 보고 분석해줘.

        [DATA 1: 스펙]
        {json.dumps(spec_data, ensure_ascii=False)}

        [DATA 2: 라이프스타일]
        {json.dumps(life_data, ensure_ascii=False)}

        [지시사항]
        1. 'keywords': 고객을 설명하는 핵심 키워드 5~7개 (예: #건성, #비건지향)
        2. 'lifestyle_summary': 생활 패턴을 3~4문장의 자연스러운 문맥으로 요약
        3. 'primary_category': 가장 필요한 제품 카테고리 1개 (영어 대문자)

        [출력 형식 (JSON)]
        {{
            "keywords": ["#키워드1", "#키워드2"],
            "lifestyle_summary": "요약 텍스트...",
            "primary_category": "CATEGORY"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",  # 혹은 gpt-5-mini 등 사용 가능한 모델
                messages=[
                    {"role": "system", "content": "You are a helpful beauty consultant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            
            return {
                "tagging_keywords": result.get('keywords', []),
                "ai_analysis_text": result.get('lifestyle_summary', ""),
                "primary_category": result.get('primary_category', "MOISTURE")
            }
        except Exception as e:
            print(f"❌ AI 분석 실패: {e}")
            return self._get_dummy_analysis()

    def _get_dummy_analysis(self):
        return {
            "tagging_keywords": ["#분석실패"],
            "ai_analysis_text": "AI 분석을 수행할 수 없습니다.",
            "primary_category": "ETC"
        }

# 싱글톤 인스턴스 (필요 시 사용)
ai_service_instance = PersonaAIService()