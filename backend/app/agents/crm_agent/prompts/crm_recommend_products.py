from typing import Dict, Any, List, Optional
import json

def build_persona_info_analysis_prompt(
          user_input: str,
          persona_info: Dict[str, Any]
          ) -> str:
    """
    페르소나 정보를 사용자 요청을 참고하여 다단계 x 다차원 분석 프롬프트
  
    Args:
        user_input: 사용자 요청
        persona_info: 메시지 생성 대상 페르소나 정보

    Returns:
        prompt
    """
    return f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 정보를 분석하여 다단계 × 다차원 분석 결과를 생성하세요.

**사용자 요청:**
{user_input}

**페르소나 정보:**
{persona_info}

---

## 분석 프레임워크

### [1단계] 다단계 페르소나 분석

1️⃣ **기본 프로필 (basic_profile)**
   - 나이, 성별, 직업에서 추론되는 라이프스타일
   - 핵심 특징 3가지

2️⃣ **라이프스타일 패턴 (lifestyle_pattern)**
   - 수면 시간, 스트레스, 디지털 기기 사용
   - 주 활동 환경에서 파악되는 환경적 요인
   - 일상 루틴의 특징

3️⃣ **뷰티 니즈 심층 분석 (beauty_needs)**
   - 피부타입 + 고민 키워드 → 핵심 니즈
   - 퍼스널 컬러 + 선호 색상 → 색조 니즈
   - 우선순위 TOP 3

4️⃣ **상황별 니즈 (situational_needs)**
   - 스킨케어 루틴 → 사용 시점/단계별 요구사항
   - 반려동물, 환경 → 특수 요구사항
   - 시간대/상황별 니즈

5️⃣ **개선 목표 (improvement_goals)**
   - 고민 키워드에서 도출되는 해결 목표
   - 가치관에서 추구하는 방향성
   - 단기/중기 목표

### [2단계] 다차원 제품 분석

🔬 **피부 과학 차원 (skin_science)**
   - 피부타입별 적합성
   - 고민 해결 메커니즘
   - 필요한 기능성 성분

🧪 **성분 차원 (ingredients)**
   - 선호 성분 매칭 (효과/안전성)
   - 기피 성분 회피 전략
   - 유효 성분 조합 추천

🌱 **라이프스타일 차원 (lifestyle)**
   - 루틴 적합성 (아침/저녁, 소요 시간)
   - 환경 적합성 (실내/야외, 계절)
   - 사용 빈도 및 편의성

💝 **감성/가치관 차원 (values_emotion)**
   - 비건, 크루얼티프리, 친환경 등 가치 매칭
   - 브랜드 철학 선호도
   - 감성적 만족 요소

🎨 **색조 차원 (color_makeup)**
   - 퍼스널 컬러 매칭
   - 베이스 호수 정보
   - 선호 색상/질감

💰 **가격/가성비 차원 (price_value)**
   - 쇼핑 스타일 & 예산 범위
   - 구매 결정 요인 (가격/품질/리뷰 등)
   - 가성비 우선순위

⚡ **사용 편의성 차원 (usability)**
   - 선호 제형/텍스처
   - 휴대성, 사용 간편성
   - 적용 시간 및 흡수력

🛡️ **안전성/리스크 차원 (safety_risk)**
   - 민감도 고려사항
   - 반려동물 안전성 (해당 시)
   - 알레르기/자극 위험 요소

---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "multi_level_analysis": {{
    "basic_profile": {{
      "inferred_lifestyle": "추론된 라이프스타일",
      "key_characteristics": ["특징1", "특징2", "특징3"]
    }},
    "lifestyle_pattern": {{
      "environmental_factors": ["요인1", "요인2"],
      "daily_routine_features": "루틴 특징 설명"
    }},
    "beauty_needs": {{
      "core_skincare_needs": ["니즈1", "니즈2"],
      "makeup_needs": ["니즈1", "니즈2"],
      "priority_top3": ["1순위", "2순위", "3순위"]
    }},
    "situational_needs": {{
      "routine_requirements": {{"morning": "아침 요구사항", "evening": "저녁 요구사항"}},
      "special_requirements": ["특수 요구사항1", "특수 요구사항2"]
    }},
    "improvement_goals": {{
      "short_term": ["단기 목표1", "단기 목표2"],
      "mid_term": ["중기 목표1", "중기 목표2"],
      "value_direction": "가치관 기반 방향성"
    }}
  }},
  "multi_dimensional_analysis": {{
    "skin_science": {{
      "skin_type_compatibility": "피부타입 적합성 설명",
      "problem_solving_mechanism": ["메커니즘1", "메커니즘2"],
      "required_functional_ingredients": ["성분1", "성분2"]
    }},
    "ingredients": {{
      "preferred_match": ["선호 성분1 + 효과", "선호 성분2 + 효과"],
      "avoid_strategy": ["기피 성분1 회피 방법", "기피 성분2 회피 방법"],
      "effective_combination": ["조합1", "조합2"]
    }},
    "lifestyle": {{
      "routine_fit": {{"morning": "아침 적합도", "evening": "저녁 적합도"}},
      "environment_fit": "환경 적합성",
      "usage_convenience": "사용 편의성 평가"
    }},
    "values_emotion": {{
      "value_match": ["가치 매칭1", "가치 매칭2"],
      "brand_philosophy_preference": "브랜드 철학 선호",
      "emotional_satisfaction": ["감성 요소1", "감성 요소2"]
    }},
    "color_makeup": {{
      "personal_color_match": "퍼스널 컬러 매칭 정보",
      "base_shade": "베이스 호수 정보",
      "preferred_colors_textures": ["색상/질감1", "색상/질감2"]
    }},
    "price_value": {{
      "budget_range": "예산 범위",
      "purchase_decision_factors": ["요인1", "요인2"],
      "value_priority": "가성비 우선순위"
    }},
    "usability": {{
      "preferred_formulation": ["제형1", "제형2"],
      "portability_convenience": "휴대성/간편성",
      "application_absorption": "적용/흡수 특성"
    }},
    "safety_risk": {{
      "sensitivity_considerations": ["고려사항1", "고려사항2"],
      "pet_safety": "반려동물 안전성 (해당 시)",
      "allergy_irritation_risks": ["위험요소1", "위험요소2"]
    }}
  }}
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- 모든 분석 항목을 빠짐없이 채워주세요.
- 페르소나 정보와 사용자 요청을 종합적으로 고려하여 분석하세요.
"""

def build_multil_query_generate_prompt(
          user_input: str,
          analysis_result: Dict[str, Any],
          product_categories: Optional[List[str]] = None
    ) -> str:
    """
    RAG 검색에 사용할 상품 멀티 쿼리 생성 프롬프트
    
    Args:
        user_input: 사용자 요청
        analysis_result: 페르소나 분석 결과
        product_categories: 메시지 생성 대상 상품 종류

    Returns:
        prompt
    """
    # 사용자가 상품 종류를 입력하지 않은 경우는 공란으로 처리
    if product_categories == None:
          product_categories = ""
    
    analysis_result = json.dumps(analysis_result, ensure_ascii=False, indent=2)

    prompt = f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 분석 결과를 바탕으로 최적의 제품을 찾기 위한 3~5개의 검색 쿼리를 생성하세요.

**사용자 요청:** {user_input}

**제품 카테고리 (필수 고려):** {product_categories}
→ 쿼리는 반드시 이 카테고리에 맞춰 생성해야 합니다.

**페르소나 분석 결과:**
{analysis_result}

---

## 쿼리 생성 가이드

### 페르소나 분석 결과 활용
위에서 제공된 페르소나 분석 결과는 이미 다단계(5단계) × 다차원(8차원) 분석이 완료된 상태입니다.
- **multi_level_analysis**: 기본 프로필, 라이프스타일 패턴, 뷰티 니즈, 상황별 니즈, 개선 목표
- **multi_dimensional_analysis**: 피부 과학, 성분, 라이프스타일, 감성/가치관, 색조, 가격/가성비, 사용 편의성, 안전성/리스크

### 제품 카테고리 최적화
**중요:** 제품 카테고리가 제공된 경우, 모든 쿼리는 해당 카테고리에 맞춰 생성해야 합니다.
- 예: "스킨케어-크림" → 크림 관련 키워드 중심 (보습, 텍스처, 흡수력 등)
- 예: "메이크업-립스틱" → 립스틱 관련 키워드 중심 (색상, 지속력, 발색 등)

### 크로스 매칭 전략
분석 결과의 여러 차원을 조합하여 **3~5개의 서로 다른 관점의 쿼리**를 생성하세요.

**쿼리 생성 원칙:**
1. 각 쿼리는 분석 결과의 2~3개 차원을 조합
2. 서로 다른 우선순위/관점 반영
3. 구체적이고 검색 가능한 키워드 사용
4. 제품 카테고리가 있다면 필수 반영

**예시 조합 패턴:**
- 쿼리1: 피부 과학 차원 + 성분 차원 + 가치관 차원
- 쿼리2: 라이프스타일 차원 + 사용 편의성 차원 + 가격 차원
- 쿼리3: 색조 차원 + 감성 차원 + 안전성 차원
- 쿼리4: 뷰티 니즈 + 선호 제형 + 루틴 적합성
- 쿼리5: 환경 적합성 + 성분 + 브랜드 가치

**쿼리 예시 (제품 카테고리: "스킨케어-크림"):**
- "건성 피부 세라마이드 고보습 크림 비건 인증"
- "저자극 수분크림 간편한 아침 루틴 가성비"
- "민감성 피부 무향 크림 반려동물 안전"

---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "queries": [
    "쿼리1: 구체적인 검색 키워드 조합",
    "쿼리2: 다른 관점의 키워드 조합",
    "쿼리3: 또 다른 관점의 키워드 조합",
    "쿼리4: 추가 관점 (선택)",
    "쿼리5: 추가 관점 (선택)"
  ]
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- queries 배열에 3~5개의 문자열을 포함하세요.
- 각 쿼리는 실제 제품 검색에 사용될 구체적인 키워드여야 합니다.
"""

    return prompt 