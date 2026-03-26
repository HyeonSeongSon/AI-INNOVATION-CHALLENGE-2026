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

페르소나 카테고리 판단
먼저 아래 기준으로 페르소나가 어떤 카테고리 상품을 원하는지 판단하세요:
- 스킨케어: 피부 고민(건조·트러블·주름·미백), 스킨케어 루틴(토너·세럼·크림)
- 색조/메이크업: 메이크업 고민(발색·지속력·커버력), 퍼스널컬러, 베이스 호수
- 메이크업 도구: 메이크업 루틴에 도구(스펀지·퍼프·브러쉬) 언급, 블렌딩·도포 고민
- 헤어: 모발/두피 고민(손상·탈모·볼륨·두피 상태), 헤어 케어 루틴
- 이너뷰티: 건강 고민(피로·수면·소화·체지방), 건강 관리 루틴(영양제 섭취)
- 향수/바디: 선호 향, 체취 고민, 바디 케어 루틴
- 네일: 손톱 고민(약함·갈라짐), 네일아트 취향, 네일 관리 루틴

페르소나 분석 기준
판단된 카테고리에 따라 아래에서 해당 항목을 우선 반영하세요.

[스킨케어] → 피부 고민 중심
  user_need_query: skin_type + skin_concerns + 케어 목적
  - skincare_routine이 스킨케어 루틴인 경우 기능 표현으로 변환
    예: 7스킨 → "얇게 여러 번 레이어링에 적합한 가벼운 제형"
    예: 원스텝 → "올인원 간편 루틴에 적합한"
  - main_environment 맥락 (실내 → 냉난방 건조, 외근 → 자외선/미세먼지)
  - stress_level, avg_sleep_hours: 피부 컨디션 영향 요소

[색조/메이크업] → 발색·마무리·지속력 중심
  user_need_query: 메이크업 고민(발색력·커버력·지속력) + 사용 목적
  - personal_color, preferred_colors → 색상 계열 니즈로 변환
  - shade_number → 베이스 호수 매칭 니즈로 변환

[메이크업 도구] → 도포 방식·블렌딩 중심
  user_need_query: 도구 사용 고민(블렌딩·도포·경계선·마무리감) + 목적
  - skincare_routine이 메이크업 루틴인 경우 도포/마무리 표현으로 변환
    예: "쿠션 후 스펀지 블렌딩" → "파운데이션·쿠션 고르게 블렌딩하는"
  - 피부 흡수·보습·성분 관련 표현 사용 금지

[헤어] → 두피/모발 고민 중심
  user_need_query: 두피 또는 모발 고민(손상·건조·탈모·볼륨 부족) + 케어 목적
  - skincare_routine이 헤어 케어 루틴인 경우 두피/모발 기능으로 변환
  - 얼굴 피부 고민 표현 사용 금지

[이너뷰티] → 건강/영양 고민 중심
  user_need_query: 건강 고민(피로·수면·소화·피부 내부 영양) + 보충 목적
  - skincare_routine이 건강 관리 루틴인 경우 섭취/영양 표현으로 변환
  - 외용(바르는) 표현 사용 금지

[향수/바디] → 향·체취·바디 케어 중심
  user_need_query: 향 선호(preferred_scents) + 바디 케어 목적

[네일] → 손톱 관리·색상 표현 중심
  user_need_query: 손톱 고민 또는 네일아트 취향 + 목적

[선호/가치관 관련] → user_preference_query에 반영 (카테고리 공통)
- preferred_ingredients, avoided_ingredients: 성분 선호/기피 (스킨케어·헤어에 해당)
- preferred_texture: 제형 선호
- preferred_scents: 향 선호 (향수·바디·헤어에 해당)
- values: 친환경 등 가치관
- personal_color, preferred_colors, shade_number: 색조 제품 해당 시 반영
- 카테고리와 무관한 항목은 포함하지 마세요

[사용자 특성 관련] → persona_query에 반영 (카테고리 공통)
- 고민 키워드 + age + occupation + main_environment + avg_sleep_hours
  * 어떤 사람인지를 설명하는 자연어 문장으로 작성
  * 성분/제형/기능 표현은 포함하지 마세요
  * 스킨케어가 아닌 경우 "~한 피부를 가진" 표현 사용 금지

작성 규칙

1. user_need_query
   - 판단된 카테고리의 핵심 고민 + 사용 목적 중심으로 작성
   - 환경 맥락과 루틴 특성에서 유추되는 기능 니즈를 포함
   - 카테고리와 무관한 고민(예: 메이크업 도구인데 피부 보습 니즈)은 제외
   - 40~60자 이내, 초과 시 선택 항목부터 제거

2. user_preference_query
   - 성분, 제형, 향, 색상, 가치관 중 카테고리에 해당하는 항목만 작성
   - avoided_ingredients는 "~프리" 형태로 표현
   - 40~60자 이내

3. retrieval_query
   - user_need_query와 user_preference_query의 핵심만 결합
   - 단순 이어붙이기 금지, 자연스러운 단일 문장으로 작성
   - 상품 설명의 combined 필드와 의미적으로 매칭되도록 작성
   - 50~80자 이내

4. persona_query
   - 사용자의 핵심 고민, 생활 패턴, 환경을 중심으로 작성
   - 상품 설명의 target_user 필드와 의미적으로 매칭되도록 작성
   - 어떤 고민을 가진 어떤 라이프스타일의 사용자인지 자연어 문장으로 작성
   - 성분, 제형, 기능 표현은 포함하지 마세요
   - 스킨케어가 아닌 경우 "피부 타입" 표현 사용 금지
   - 30~50자 이내

공통 주의사항
- 특정 브랜드나 상품명을 포함하지 마세요
- purchase_decision_factors는 쿼리에 직접 반영하지 않습니다 (리랭크 가중치로 별도 활용)
- 판단된 카테고리와 맞지 않는 항목은 비중을 낮추거나 제외하세요

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
