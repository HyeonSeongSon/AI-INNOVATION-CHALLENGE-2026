import json
from typing import Dict, Union


def build_generate_product_search_query_from_persona_prompt(persona_info: Union[dict, str]) -> Dict:
    if isinstance(persona_info, dict):
        persona_str = json.dumps(persona_info, ensure_ascii=False, indent=2)
    else:
        persona_str = str(persona_info)

    prompt = f"""
당신은 뷰티 상품 추천 시스템을 위한 검색 쿼리 생성 전문가입니다.
주어진 페르소나 정보를 분석하여 상품 검색에 사용할 쿼리를 생성하세요.

추천 시스템 구조
1. Retrieval 단계: retrieval_query로 상품 후보를 검색
2. Rerank 단계
   - user_need_query    → product_function_desc 매칭
   - user_preference_query → product_attribute_desc 매칭
   - persona_query      → product_target_user 매칭

페르소나 분석 기준
페르소나 정보를 아래 기준으로 분류하여 쿼리에 반영하세요.

[기능/니즈 관련] → user_need_query에 반영
- skin_type, skin_concerns: 피부 고민과 해결 목적
- skincare_routine: 루틴 방식을 상품 기능 표현으로 변환
  예: 7스킨 → "얇게 여러 번 레이어링에 적합한 가벼운 제형"
  예: 원스텝 → "올인원 간편 루틴에 적합한"
  예: 더블클렌징 → "메이크업 잔여물 제거"
  * 루틴 이름을 그대로 쓰지 말고 반드시 기능/제형 표현으로 변환하세요
- main_environment: 환경 맥락 (예: 실내 → 냉난방 건조, 외근 → 자외선/미세먼지)
- stress_level, avg_sleep_hours: 피부 컨디션 영향 요소

[선호/가치관 관련] → user_preference_query에 반영
- preferred_ingredients, avoided_ingredients: 성분 선호/기피
- preferred_texture: 제형 선호
- preferred_scents: 향 선호
- values: 친환경 등 가치관
- personal_color, preferred_colors, shade_number: 색조 제품 해당 시 반영

[사용자 특성 관련] → persona_query에 반영
- skin_type, skin_concerns: 피부 타입과 고민
- age, occupation: 연령대와 생활 패턴
- skincare_routine: 루틴 방식 (기능 변환 없이 그대로 반영)
- main_environment: 주요 생활 환경
- stress_level, avg_sleep_hours: 생활 컨디션
  * 어떤 사람인지를 설명하는 자연어 문장으로 작성
  * 성분/제형/기능 표현은 포함하지 마세요

작성 규칙

1. user_need_query
   - 피부 고민, 효과, 케어 목적 중심으로 작성
   - 환경 맥락과 루틴 특성에서 유추되는 기능 니즈를 포함
   - 필수: skin_type + skin_concerns + 케어 목적
   - 선택: 루틴/환경 맥락 (위 내용이 길어지면 생략)
   - 40~60자 이내, 초과 시 선택 항목부터 제거

2. user_preference_query
   - 성분, 제형, 향, 색상, 가치관 중심으로 작성
   - avoided_ingredients는 "~프리" 형태로 표현
   - 40~60자 이내

3. retrieval_query
   - user_need_query와 user_preference_query의 핵심만 결합
   - 단순 이어붙이기 금지, 자연스러운 단일 문장으로 작성
   - 상품 설명의 combined 필드와 의미적으로 매칭되도록 작성
   - 50~80자 이내

4. persona_query
   - 사용자의 피부 타입, 고민, 생활 패턴, 환경을 중심으로 작성
   - 상품 설명의 target_user 필드와 의미적으로 매칭되도록 작성
   - "~한 피부를 가진 ~한 환경의 사용자" 형태의 자연어 문장
   - 성분, 제형, 기능 표현은 포함하지 마세요
   - 30~50자 이내

공통 주의사항
- 특정 브랜드나 상품명을 포함하지 마세요
- 다양한 뷰티 카테고리(스킨, 헤어, 바디, 향수 등)에 적용 가능하도록 작성하세요
- purchase_decision_factors는 쿼리에 직접 반영하지 않습니다 (리랭크 가중치로 별도 활용)
- 페르소나에 해당 없는 항목(예: 색조 정보인데 스킨케어 니즈가 강한 경우)은 비중을 낮추세요

출력 형식 (JSON만 출력, 설명 없음)
{{
  "need": "",
  "preference": "",
  "retrieval": "",
  "persona": ""
}}

Persona:
{persona_str}
"""
    return prompt
