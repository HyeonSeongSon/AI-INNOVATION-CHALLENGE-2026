from typing import Dict, Any, List, Optional
import json

def build_persona_needs_analysis_prompt(
        persona_info: str,
        ) -> str:
    prompt = f"""
당신은 뷰티 제품 추천 시스템에서 페르소나를 분석하여
사용자의 구매 니즈를 도출하는 전문가입니다.

주어진 페르소나 정보를 기반으로 사용자의 스킨케어 및 메이크업 관련 니즈를 분석하세요.
니즈 분석 결과는 제품 검색에 사용할 멀티 쿼리 생성에 사용됩니다.

분석 시 다음 원칙을 따르세요.

1. 페르소나 정보에서 명시적으로 나타난 니즈뿐 아니라
   라이프스타일, 피부 상태, 취향을 고려하여 잠재 니즈까지 추론합니다.

2. 니즈는 실제 상품 추천에 활용될 수 있도록
   기능적 니즈, 제품 특성 니즈, 성분 니즈, 감성 니즈로 구분합니다.

3. 각 니즈는 구체적인 제품 특성으로 연결될 수 있어야 합니다.

4. 니즈는 중요도 순으로 정리합니다.

5. 제품 설명에 등장하는 표현들을 사용해주세요.

출력 형식은 반드시 JSON으로 작성하세요.

출력 구조:

{{
  "core_needs": [],
  "skin_needs": [],
  "ingredient_preferences": {{
    "preferred": [],
    "avoided": []
  }},
  "product_texture_preferences": [],
  "lifestyle_needs": [],
  "emotional_needs": [],
  "fragrance_preferences": {{}},
  "makeup_color_preferences": [],
  "purchase_decision_factors": [],
  "recommended_product_features": []
}}

각 항목 설명:

core_needs:
사용자의 가장 중요한 핵심 니즈 (3~5개)

skin_needs:
피부 상태 기반 기능적 니즈

ingredient_preferences:
선호 성분과 기피 성분

product_texture_preferences:
선호 제형 및 사용감

lifestyle_needs:
사용자의 생활 패턴에서 파생되는 니즈

emotional_needs:
사용자가 중요하게 생각하는 가치 또는 감성적 니즈

fragrance_preferences:
선호 향과 향 강도

makeup_color_preferences:
어울리는 메이크업 컬러

purchase_decision_factors:
구매 시 중요하게 보는 요소

recommended_product_features:
상품 검색 및 추천에 사용할 수 있는 제품 특성 키워드

다음 페르소나 정보를 분석하세요.

[페르소나 정보]
{persona_info}
"""
    return prompt


def build_analysis_prompt(persona_info: Dict[str, Any]) -> str:
    """
    다단계 × 다차원 분석을 위한 프롬프트 구성
    """
    populated_fields = _extract_populated_fields(persona_info)
    persona_info_str = json.dumps(persona_info, ensure_ascii=False, indent=2)
    prompt = _build_persona_info_analysis_prompt(persona_info_str, populated_fields)
    return prompt

def _extract_populated_fields(persona_info: Dict[str, Any]) -> Dict[str, bool]:
    """
    PersonaInfo dict에서 실제 데이터가 있는 필드와 빈 필드를 분류.
    LLM 프롬프트에 전달하여 추론 범위를 명시하는 데 사용됨.
    """
    list_fields = [
        "피부타입", "고민 키워드", "메이크업 선호 색상",
        "선호 성분", "기피 성분", "선호 향", "가치관",
        "선호 제형(텍스처)", "구매 결정 요인",
    ]
    str_fields = [
        "퍼스널 컬러", "베이스 호수", "스킨케어 루틴",
        "주 활동 환경", "반려동물", "수면 시간",
        "스트레스", "디지털 기기 사용", "쇼핑 스타일&예산",
    ]
    result: Dict[str, bool] = {}
    for f in list_fields:
        result[f] = bool(persona_info.get(f))  # 빈 리스트 [] → False
    for f in str_fields:
        val = persona_info.get(f)
        result[f] = bool(val and str(val).strip())  # None / "" → False
    return result

def _build_persona_info_analysis_prompt(
          persona_info: str,
          populated_fields: Dict[str, bool]
          ) -> str:
    """
    페르소나 정보를 사용자 요청을 참고하여 다단계 x 다차원 분석 프롬프트

    Args:
        persona_info: 메시지 생성 대상 페르소나 정보 (JSON 문자열)
        populated_fields: 실제 데이터가 있는 필드 여부 맵 (필드명 → bool)

    Returns:
        prompt
    """
    has_data = [f for f, v in populated_fields.items() if v]
    no_data  = [f for f, v in populated_fields.items() if not v]

    data_status_section = f"""## 실제 데이터 현황
아래는 페르소나 DB에 실제 입력된 데이터의 존재 여부입니다.

- **데이터 있음** ({len(has_data)}개): {', '.join(has_data) if has_data else '없음'}
- **데이터 없음** ({len(no_data)}개): {', '.join(no_data) if no_data else '없음'}

분석 시 이 현황을 반드시 참고하세요."""

    return f"""당신은 피부 과학, 화장품 성분, 뷰티 트렌드에 전문 지식을 가진 뷰티 분석 전문가입니다.

입력된 페르소나 정보를 기반으로 해당 인물의 뷰티 특성과 니즈를 분석하여
**다단계 × 다차원 분석 결과**를 생성하세요.

사용자 요청은 존재하지 않으며,
**페르소나 정보만으로 잠재 니즈까지 추론하는 것이 목표입니다.**

---

{data_status_section}

---

페르소나 정보:
{persona_info}

---

## 분석 프레임워크

### [1단계] 다단계 페르소나 분석

1️⃣ 기본 프로필 (basic_profile)

페르소나의 나이, 성별, 직업, 관심사, 생활환경을 기반으로
추론 가능한 라이프스타일을 분석하세요.

분석 내용
- 라이프스타일 추론
- 핵심 특징 3가지


2️⃣ 라이프스타일 패턴 (lifestyle_pattern)

생활 습관과 환경을 기반으로
피부 상태와 뷰티 루틴에 영향을 미치는 요인을 분석하세요.

분석 내용
- 환경적 요인
- 스트레스 및 생활 패턴
- 디지털 기기 사용
- 활동 환경
- 일상 루틴 특징


3️⃣ 뷰티 니즈 심층 분석 (beauty_needs)

페르소나의 피부타입, 고민 키워드, 관심사 등을 기반으로
핵심 뷰티 니즈를 도출하세요.

분석 내용
- 스킨케어 핵심 니즈
- 색조 니즈
- 잠재 니즈 (latent needs)
- 우선순위 TOP 3


4️⃣ 상황별 니즈 (situational_needs)

시간대와 상황에 따라 필요한 뷰티 요구사항을 분석하세요.

분석 내용
- 스킨케어 루틴 요구사항
- 환경 기반 니즈
- 특수 상황 니즈
- 시간대별 니즈


5️⃣ 개선 목표 (improvement_goals)

페르소나의 고민과 가치관을 기반으로
단기 및 중기 개선 목표를 도출하세요.

분석 내용
- 단기 목표
- 중기 목표
- 추구하는 뷰티 방향성

---

### [2단계] 다차원 뷰티 분석

🔬 피부 과학 차원 (skin_science)

분석 내용
- 피부타입 적합성
- 피부 고민 해결 메커니즘
- 필요한 기능성 성분


🧪 성분 차원 (ingredients)

분석 내용
- 선호 성분 매칭
- 기피 성분 회피 전략
- 효과적인 성분 조합


🌱 라이프스타일 차원 (lifestyle)

분석 내용
- 루틴 적합성
- 환경 적합성
- 사용 편의성


💝 감성 / 가치관 차원 (values_emotion)

분석 내용
- 가치관 기반 제품 선호
- 브랜드 철학 선호
- 감성적 만족 요소


🎨 색조 차원 (color_makeup)

분석 내용
- 퍼스널 컬러 추론
- 베이스 컬러 적합성
- 선호 색상 및 질감


💰 가격 / 소비 행동 차원 (price_value)

분석 내용
- 예산 범위 추정
- 구매 행동 특징
- 구매 결정 요인


⚡ 사용 편의성 차원 (usability)

분석 내용
- 선호 제형
- 사용 편의성
- 흡수력 및 발림성


🛡 안전성 / 리스크 차원 (safety_risk)

분석 내용
- 민감 피부 고려사항
- 알레르기 위험
- 자극 가능 성분

---

## 출력 형식

반드시 아래 JSON 형식으로만 응답하세요.

{{
  "multi_level_analysis": {{
    "basic_profile": {{
      "inferred_lifestyle": "",
      "key_characteristics": []
    }},
    "lifestyle_pattern": {{
      "environmental_factors": [],
      "daily_routine_features": ""
    }},
    "beauty_needs": {{
      "core_skincare_needs": [],
      "makeup_needs": [],
      "latent_needs": [],
      "priority_top3": []
    }},
    "situational_needs": {{
      "routine_requirements": {{
        "morning": "",
        "evening": ""
      }},
      "special_requirements": []
    }},
    "improvement_goals": {{
      "short_term": [],
      "mid_term": [],
      "value_direction": ""
    }}
  }},
  "multi_dimensional_analysis": {{
    "skin_science": {{
      "skin_type_compatibility": "",
      "problem_solving_mechanism": [],
      "required_functional_ingredients": []
    }},
    "ingredients": {{
      "preferred_match": [],
      "avoid_strategy": [],
      "effective_combination": []
    }},
    "lifestyle": {{
      "routine_fit": {{
        "morning": "",
        "evening": ""
      }},
      "environment_fit": "",
      "usage_convenience": ""
    }},
    "values_emotion": {{
      "value_match": [],
      "brand_philosophy_preference": "",
      "emotional_satisfaction": []
    }},
    "color_makeup": {{
      "personal_color_match": "",
      "base_shade": "",
      "preferred_colors_textures": []
    }},
    "price_value": {{
      "budget_range": "",
      "purchase_decision_factors": [],
      "value_priority": ""
    }},
    "usability": {{
      "preferred_formulation": [],
      "portability_convenience": "",
      "application_absorption": ""
    }},
    "safety_risk": {{
      "sensitivity_considerations": [],
      "pet_safety": "",
      "allergy_irritation_risks": []
    }}
  }},
  "inferred_dimensions": [],
  "search_keywords": {{
    "핵심_키워드": [],
    "추가_키워드": [],
    "제외_키워드": [],
    "추천_쿼리_힌트": []
  }}
}}

---

## 중요 규칙

1. 반드시 JSON 형식으로만 응답하세요.
2. 모든 항목을 빠짐없이 채워야 합니다.
3. **데이터 있음** 필드는 페르소나 정보를 그대로 사용하세요. 임의로 변경하거나 확장하지 마세요.
4. **데이터 없음** 필드는 뷰티 산업 일반 패턴으로 추론할 수 있습니다. 단, 추론을 사용한 차원(dimension)은 반드시 `inferred_dimensions` 배열에 해당 키를 포함시키세요.
   - 추론 사용 차원 예시: `"ingredients"`, `"color_makeup"`, `"price_value"` 등
   - 실제 데이터만으로 분석한 차원은 `inferred_dimensions`에 포함하지 마세요.
5. 분석 결과는 **실제 뷰티 제품 추천 시스템에 활용 가능해야 합니다.**
6. `search_keywords`는 위 13개 차원 전체를 종합하여 벡터 검색에 최적화된 키워드를 추출하세요.
   - `핵심_키워드` (3-5개): 모든 차원의 핵심을 관통하는 가장 중요한 벡터 검색 키워드 (예: "건성피부", "세라마이드", "고보습")
   - `추가_키워드` (2-4개): 쿼리 다양화를 위한 보조 키워드 (예: "저자극", "무향", "빠른흡수")
   - `제외_키워드`: 기피 성분 분석에서 도출된 제외어 (기피 성분이 없으면 빈 배열)
   - `추천_쿼리_힌트` (2-3개): 핵심·추가 키워드를 조합한 실제 벡터 검색 쿼리 예시 문자열
   - **반드시 상품 설명 문서에 실제로 등장할 수 있는 키워드만 사용하세요.**
     포함 가능: 성분명, 피부타입, 피부고민, 제형, 기능, 퍼스널컬러, 향, 가치관(비건·친환경 등)
     사용 금지: "베스트셀러", "후기 상위", "임상 검증", "비포애프터" 등 리뷰·마케팅 표현
"""

def build_multi_query_generate_prompt(
          user_input: str,
          query_context: Dict[str, Any],
          product_categories: Optional[List[str]] = None,
          persona_info: Optional[Dict[str, Any]] = None,
    ) -> str:
    """
    RAG 검색에 사용할 상품 멀티 쿼리 생성 프롬프트

    Args:
        user_input: 사용자 요청
        query_context: 페르소나 분석 결과에서 추출한 압축 컨텍스트
                       (search_keywords 또는 규칙 기반 핵심 필드)
        product_categories: 메시지 생성 대상 상품 종류
        persona_info: 원본 페르소나 정보 (퍼스널컬러, 고민키워드 등을 쿼리에 직접 반영)

    Returns:
        prompt
    """
    # 사용자가 상품 종류를 입력하지 않은 경우는 공란으로 처리
    if product_categories is None:
          product_categories = ""

    # 데이터 신뢰도 안내: search_keywords 방식이면 간략히, fallback이면 inferred_dimensions 표시
    search_keywords = query_context.get("search_keywords")
    if search_keywords:
        data_reliability_section = "## 데이터 신뢰도 안내\n페르소나 분석 전 차원을 종합한 핵심 키워드가 제공됩니다."
    else:
        inferred_dimensions = query_context.get("inferred_dimensions", [])
        all_dimensions = [
            "skin_science", "ingredients", "lifestyle", "values_emotion",
            "color_makeup", "price_value", "usability", "safety_risk",
        ]
        data_based_dimensions = [d for d in all_dimensions if d not in inferred_dimensions]
        if inferred_dimensions:
            data_reliability_section = f"""## 데이터 신뢰도 안내
- **실제 페르소나 데이터 기반** (우선 활용): {', '.join(data_based_dimensions)}
- **LLM 추론 기반** (보조적 활용): {', '.join(inferred_dimensions)}

→ 실제 데이터 기반 항목을 중심으로 쿼리를 구성하세요."""
        else:
            data_reliability_section = "## 데이터 신뢰도 안내\n모든 분석 항목이 실제 페르소나 데이터를 기반으로 합니다."

    query_context_str = json.dumps(query_context, ensure_ascii=False, indent=2)

    # 페르소나 원본 데이터에서 핵심 필터 항목 추출
    persona_context_section = ""
    if persona_info:
        personal_color = persona_info.get("퍼스널 컬러")
        skin_concerns = persona_info.get("고민 키워드") or []
        skin_type = persona_info.get("피부타입") or []
        avoided_ingredients = persona_info.get("기피 성분") or []

        lines = []
        if personal_color:
            lines.append(f"- 퍼스널컬러: {personal_color}")
        if skin_type:
            lines.append(f"- 피부타입: {', '.join(skin_type)}")
        if skin_concerns:
            lines.append(f"- 고민키워드: {', '.join(skin_concerns)}")
        if avoided_ingredients:
            lines.append(f"- 기피성분(쿼리에서 제외): {', '.join(avoided_ingredients)}")

        if lines:
            persona_context_section = f"""## 페르소나 핵심 속성 (쿼리에 직접 반영 필수)
{chr(10).join(lines)}

→ 위 속성들을 최소 2개 이상의 쿼리에 명시적으로 포함하세요.
→ 예: 퍼스널컬러가 '쿨톤'이면 "쿨톤 적합" 또는 "블루베이스", 고민키워드가 '모공'이면 "모공 케어" 같은 식으로 반영하세요.
"""

    prompt = f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 분석 결과를 바탕으로 최적의 제품을 찾기 위한 3~5개의 검색 쿼리를 생성하세요.

**사용자 요청:** {user_input}

**제품 카테고리 (필수 고려):** {product_categories}
→ 쿼리는 반드시 이 카테고리에 맞춰 생성해야 합니다.

{persona_context_section}{data_reliability_section}

**페르소나 분석 요약 (쿼리 생성용):**
{query_context_str}

---

## 쿼리 생성 가이드

### 핵심 키워드 활용
위에서 제공된 페르소나 분석 요약을 기반으로 쿼리를 생성하세요.
- `search_keywords`가 있는 경우: `핵심_키워드`를 중심으로 활용하고, `추천_쿼리_힌트`를 참고하여 더 다양한 각도로 변형하세요.
- 추가 필드(top_priorities, preferred_ingredients 등)가 있는 경우: 해당 내용을 조합하여 쿼리를 구성하세요.

### 제품 카테고리 최적화
**중요:** 제품 카테고리가 제공된 경우, 모든 쿼리는 해당 카테고리에 맞춰 생성해야 합니다.
- 예: "스킨케어-크림" → 크림 관련 키워드 중심 (보습, 텍스처, 흡수력 등)
- 예: "메이크업-립스틱" → 립스틱 관련 키워드 중심 (색상, 지속력, 발색 등)

### 크로스 매칭 전략
제공된 키워드와 속성을 조합하여 **3~5개의 서로 다른 관점의 쿼리**를 생성하세요.

**쿼리 생성 원칙:**
1. 각 쿼리는 2~3개 키워드/속성을 조합
2. 서로 다른 우선순위/관점 반영
3. 구체적이고 검색 가능한 키워드 사용
4. 제품 카테고리가 있다면 필수 반영
5. 일관성 있는 키워드들을 사용하여 포커스 있는 쿼리 생성

**쿼리 예시 (제품 카테고리: "스킨케어-크림"):**
- "건성 피부 세라마이드 고보습 크림 비건 인증"
- "저자극 수분크림 간편한 아침 루틴 가성비"
- "민감성 피부 무향 크림 반려동물 안전"

---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "queries": [
    "건성 피부 세라마이드 고보습 크림 저자극",
    "웜톤 적합 수분크림 히알루론산 무향 파라벤 프리",
    "민감성 피부 판테놀 진정 크림 친환경 비건"
  ]
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- queries 배열에 3~5개의 문자열을 포함하세요.
- 각 쿼리는 **키워드만** 담은 순수 문자열이어야 합니다. "쿼리1:", "쿼리2:" 같은 접두사를 절대 포함하지 마세요.
- 각 쿼리는 성분명·피부타입·제형·기능·가치관 등 **상품 설명 문서에 실제로 등장할 수 있는 키워드**로만 구성하세요.
- "베스트셀러", "후기 상위", "임상 검증", "비포애프터" 등 리뷰·마케팅 표현은 사용하지 않은 상품 관련 쿼리로 작성하시오.
"""

    return prompt 


def build_needs_multi_query_generate_prompt(user_input, query_context, product_categories):
    prompt = f"""당신은 뷰티 전문가입니다. 사용자의 요청과 페르소나 분석 결과를 바탕으로 최적의 제품을 찾기 위한 3~5개의 검색 쿼리를 생성하세요.

**사용자 요청:** {user_input}

**제품 카테고리 (필수 고려):** {product_categories}
→ 쿼리는 반드시 이 카테고리에 맞춰 생성해야 합니다.

**페르소나 분석 니즈 (쿼리 생성용):**
{query_context}

---

## 쿼리 생성 가이드

### 핵심 키워드 활용
위에서 제공된 페르소나 니즈 분석을 기반으로 쿼리를 생성하세요.
- core_needs를 중심으로 멀티 쿼리를 생성
- product_texture_preferences, lifestyle_needs, emotional_needs 등은 제품 카테고리를 고려하여 활용(스킨, 앰플 같은 제품은 makeup_color_preferences 사용 하지 않음)
- 핵심 키워드에는 있지만 제품 카테고리와 관련 없는 내용은 멀티 쿼리 생성에서 제외

### 제품 카테고리 최적화
**중요:** 제품 카테고리가 제공된 경우, 모든 쿼리는 해당 카테고리에 맞춰 생성해야 합니다.
- 예: "스킨케어-크림" → 크림 관련 키워드 중심 (보습, 텍스처, 흡수력 등)
- 예: "메이크업-립스틱" → 립스틱 관련 키워드 중심 (색상, 지속력, 발색 등)

### 크로스 매칭 전략
제공된 키워드와 속성을 조합하여 **3~5개의 서로 다른 관점의 쿼리**를 생성하세요.

**쿼리 생성 원칙:**
1. 각 쿼리는 2~3개 키워드/속성을 조합
2. 서로 다른 우선순위/관점 반영
3. 구체적이고 검색 가능한 키워드 사용
4. 제품 카테고리가 있다면 필수 반영
5. 일관성 있는 키워드들을 사용하여 각각 다른 포인트가 있는 쿼리 생성
6. 한번 사용한 키워드는 다른 쿼리에서 사용하지 않음
7. 벡터 임베딩 의도 캡처가 가능하며, 성분+기능+속성 구조의 5~7토큰 쿼리 생성 

**쿼리 예시 (제품 카테고리: "스킨&토너"):**
- "스킨 토너 히알루론산 멀티분자 워터베이스 오일프리 무향"
- "스킨 토너 살리실산 0.5-2% 피지조절 논코메도제닉",
- "스킨 토너 니아신아마이드 2-5% 트러블자국 케어 저자극 무알콜",
- "스킨 토너 센텔라아시아티카 판테놀 진정 천연유래 무향"
- "스킨 토너 빠른흡수 워터리 가벼운제형 무끈적 데일리"

각각의 쿼리 포인트는 Q1(수분/보습), Q2(피지조절), Q3(트러블자국), Q4(진정/가치관), Q5(질감/사용편의) — 5개 쿼리가 모두 다른 각도, 중복 키워드 X
---

## 출력 형식 (JSON)

다음 형식으로 응답하세요:

{{
  "queries": [
    "건성 피부 세라마이드 고보습 크림 저자극",
    "웜톤 적합 수분크림 히알루론산 무향 파라벤 프리",
    "민감성 피부 판테놀 진정 크림 친환경 비건"
  ]
}}

**중요:**
- 반드시 JSON 형식으로만 응답하세요.
- queries 배열에 3~5개의 문자열을 포함하세요.
- 각 쿼리는 **키워드만** 담은 순수 문자열이어야 합니다. "쿼리1:", "쿼리2:" 같은 접두사를 절대 포함하지 마세요.
- 각 쿼리는 성분명·피부타입·제형·기능·가치관 등 **상품 설명 문서에 실제로 등장할 수 있는 키워드**로만 구성하세요.
- "베스트셀러", "후기 상위", "임상 검증", "비포애프터", "가성비" 등 리뷰·마케팅 표현 언어은 사용하지 않은 상품 관련 쿼리로 작성하시오.
"""
    return prompt