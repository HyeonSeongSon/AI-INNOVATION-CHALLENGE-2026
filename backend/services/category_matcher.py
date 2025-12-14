import json
from typing import List, Tuple
from models.persona import PersonaInput, CategoryResult
import openai 

class CategoryMatcher:
    def __init__(self):
        # 팀원과 합의된 공통 카테고리 코드 (DB와 일치)
        self.CATEGORY_MAP = {
            "MOISTURE": ["건성", "속건조", "당김", "각질", "히알루론산", "수분"],
            "TROUBLE": ["지성", "여드름", "트러블", "피지", "티트리", "시카", "진정"],
            "PORE": ["모공", "블랙헤드", "나비존", "요철"],
            "AGING": ["주름", "탄력", "노화", "레티놀", "콜라겐", "리프팅"],
            "BRIGHTENING": ["미백", "기미", "잡티", "칙칙함", "비타민C", "톤업"]
        }
        # API 키 (실제 환경에서는 .env 파일에서 불러오는 것을 권장)
        self.client = openai.OpenAI(api_key="sk-...") 

    async def analyze(self, persona: PersonaInput) -> CategoryResult:
        """
        하이브리드 분석: 룰 베이스 점수 산정 -> LLM 최종 판단
        """
        # 1. 룰 베이스: 후보군 압축 (LLM에게 힌트로 제공)
        candidates = self._calculate_rule_base_scores(persona)
        top_candidate_str = ", ".join([f"{c[0]}({c[1]}점)" for c in candidates[:2]])

        # 2. LLM 에이전트: 최종 판단
        final_result = await self._ask_llm_agent(persona, top_candidate_str)
        return final_result

    def _calculate_rule_base_scores(self, persona: PersonaInput) -> List[Tuple[str, int]]:
        scores = {cat: 0 for cat in self.CATEGORY_MAP.keys()}
        
        # 분석 대상 텍스트 통합
        user_keywords = [persona.skinType, persona.sensitivityLevel] + persona.skinConcerns + persona.preferredIngredients
        
        for cat, keywords in self.CATEGORY_MAP.items():
            for k in keywords:
                # 키워드 포함 여부 체크
                count = sum(1 for data in user_keywords if data and k in str(data))
                scores[cat] += count

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    async def _ask_llm_agent(self, persona: PersonaInput, candidates_hint: str) -> CategoryResult:
        # [업그레이드] Few-Shot Prompting 적용 (예시 제공)
        prompt = f"""
        당신은 스킨케어 전문가 에이전트입니다. 사용자의 정보를 분석해 가장 적합한 '단 하나의 상품 카테고리'를 추천하세요.

        [분석 예시 (Few-Shot)]
        Case 1:
        - 입력: 30대 여성, 건성, 고민(주름, 속건조), 레티놀 선호
        - 룰 베이스 힌트: AGING(4점), MOISTURE(3점)
        - 결과: {{ "primary_category": "AGING", "reasoning": "속건조와 함께 주름 고민이 깊어지는 시기로, 초기 안티에이징 관리가 가장 시급합니다." }}

        Case 2:
        - 입력: 20대 남성, 지성, 고민(여드름, 개기름), 티트리 선호
        - 룰 베이스 힌트: TROUBLE(5점), PORE(2점)
        - 결과: {{ "primary_category": "TROUBLE", "reasoning": "과다 피지로 인한 트러블 발생 빈도가 높아 진정 케어가 1순위입니다." }}

        [실제 사용자 분석 요청]
        - 나이/성별: {persona.age}, {persona.gender}
        - 피부타입: {persona.skinType}
        - 고민: {', '.join(persona.skinConcerns)}
        - 특징: 직업({persona.occupation}), 민감도({persona.sensitivityLevel}), 수분도({persona.moistureLevel}%)
        - 룰 베이스 힌트: {candidates_hint}
        - 가능 카테고리: {', '.join(self.CATEGORY_MAP.keys())}

        위 사용자에 맞는 결과를 JSON으로 출력하세요.
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "JSON 형식으로만 답하세요."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            result_json = json.loads(response.choices[0].message.content)
            
            return CategoryResult(
                primary_category=result_json.get("primary_category", "MOISTURE"),
                reasoning=result_json.get("reasoning", "피부 타입 맞춤 추천"),
                confidence_score=0.95
            )
        except Exception as e:
            print(f"LLM Error: {e}")
            fallback = candidates_hint.split("(")[0].strip() if candidates_hint else "MOISTURE"
            return CategoryResult(primary_category=fallback, reasoning="데이터 기반 자동 추천 (AI 응답 지연)", confidence_score=0.7)