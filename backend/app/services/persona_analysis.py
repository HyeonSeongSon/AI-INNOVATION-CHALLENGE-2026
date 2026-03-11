"""
페르소나 다단계×다차원 분석 서비스
CRM agent의 build_persona_info_analysis_prompt를 활용한 사전 분석 캐싱
"""

import os
import json
import time
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from app.core.logging import get_logger

logger = get_logger("persona_analysis")


def build_persona_info_analysis_prompt(persona_info: Dict[str, Any]) -> str:
    """
    페르소나 정보를 기반으로 다단계 × 다차원 분석 프롬프트 생성
    (backend/app/agents/crm_agent/prompts/crm_recommend_products.py와 동일)
    """
    return f"""당신은 피부 과학, 화장품 성분, 뷰티 트렌드에 전문 지식을 가진 뷰티 분석 전문가입니다.

입력된 페르소나 정보를 기반으로 해당 인물의 뷰티 특성과 니즈를 분석하여
**다단계 × 다차원 분석 결과**를 생성하세요.

사용자 요청은 존재하지 않으며,
**페르소나 정보만으로 잠재 니즈까지 추론하는 것이 목표입니다.**

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
3. 페르소나 정보 기반 **합리적 추론**을 수행하세요.
4. 명확하지 않은 정보는 **뷰티 산업 일반 패턴 기반으로 추론**하세요. 단, 추론을 사용한 차원(dimension)은 반드시 `inferred_dimensions` 배열에 해당 키를 포함시키세요.
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


def _map_to_persona_info(persona_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    페르소나 생성 데이터(영문 키) → CRM agent 표준 한국어 키 딕셔너리 변환
    backend/app/agents/crm_agent/services/recommend_products.py의 get_persona_info()와 동일한 매핑
    """
    avg_sleep = persona_data.get("avg_sleep_hours")
    digital_usage = persona_data.get("digital_device_usage_time")

    return {
        "이름": persona_data.get("name"),
        "나이": persona_data.get("age"),
        "성별": persona_data.get("gender"),
        "직업": persona_data.get("occupation"),
        "피부타입": persona_data.get("skin_type", []),
        "고민 키워드": persona_data.get("skin_concerns", []),
        "퍼스널 컬러": persona_data.get("personal_color"),
        "베이스 호수": persona_data.get("shade_number"),
        "메이크업 선호 색상": persona_data.get("preferred_colors", []),
        "선호 성분": persona_data.get("preferred_ingredients", []),
        "기피 성분": persona_data.get("avoided_ingredients", []),
        "선호 향": persona_data.get("preferred_scents", []),
        "가치관": persona_data.get("values", []),
        "스킨케어 루틴": persona_data.get("skincare_routine"),
        "주 활동 환경": persona_data.get("main_environment"),
        "선호 제형(텍스처)": persona_data.get("preferred_texture", []),
        "반려동물": persona_data.get("pets"),
        "수면 시간": f"{avg_sleep}시간" if avg_sleep else None,
        "스트레스": persona_data.get("stress_level"),
        "디지털 기기 사용": f"하루 {digital_usage}시간" if digital_usage else None,
        "쇼핑 스타일&예산": persona_data.get("shopping_style"),
        "구매 결정 요인": persona_data.get("purchase_decision_factors", []),
    }


async def run_persona_analysis(persona_data: Dict[str, Any], model: Optional[str] = None) -> Dict[str, Any]:
    """
    페르소나 데이터로 다단계×다차원 분석 실행

    Args:
        persona_data: 페르소나 생성에 사용된 데이터 (영문 키)
        model: OpenAI 모델명 (None이면 환경변수 사용)

    Returns:
        multi_level_analysis + multi_dimensional_analysis 딕셔너리
    """
    model_name = model or os.getenv("CHATGPT_MODEL_NAME", "gpt-5-mini")
    persona_name = persona_data.get("name", "unknown")

    logger.info("persona_analysis_started", persona_name=persona_name, model=model_name)
    start = time.perf_counter()

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # 영문 키 → 한국어 키 변환
    persona_info = _map_to_persona_info(persona_data)
    persona_info_str = json.dumps(persona_info, ensure_ascii=False, indent=2)

    # 분석 프롬프트 생성
    prompt = build_persona_info_analysis_prompt(persona_info_str)

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.error("persona_analysis_llm_failed", persona_name=persona_name, model=model_name, duration_ms=duration_ms, error_type=type(e).__name__, error_message=str(e), exc_info=True)
        raise

    content = response.choices[0].message.content.strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.warning("persona_analysis_json_parse_failed", persona_name=persona_name, duration_ms=duration_ms, error_message=str(e))
        result = {
            "multi_level_analysis": {},
            "multi_dimensional_analysis": {},
        }

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info("persona_analysis_completed", persona_name=persona_name, model=model_name, duration_ms=duration_ms)

    return result
