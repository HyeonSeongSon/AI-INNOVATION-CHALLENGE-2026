"""
피드백 기반 메시지 수정 프롬프트

기존 메시지를 처음부터 재생성하지 않고, 피드백에서 지적된 부분만 수정한다.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
from typing import List, Dict, Any, Optional

_FEEDBACK_PRODUCT_FIELDS = {
    "product_name", "brand", "product_tag",
    "concern", "key_benefits", "target_user",
    "ingredients", "features", "description",
    "skin_type", "volume", "usage",
    "price", "discount_rate",
}


def _filter_product_info(product_info: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in product_info.items() if k in _FEEDBACK_PRODUCT_FIELDS and v}


def build_apply_feedback_prompt(
    existing_title: str,
    existing_message: str,
    feedback: str,
    brand_tone: str,
    product_info: Dict[str, Any],
    persona_info: Optional[Dict[str, Any]] = None,
) -> List:
    """
    피드백 반영 메시지 수정 프롬프트 구성

    Args:
        existing_title:   수정 대상 메시지 제목
        existing_message: 수정 대상 메시지 본문
        feedback:         품질 검사에서 도출된 피드백 텍스트
        brand_tone:       브랜드 톤 가이드
        product_info:     상품 정보 dict (사실 기반 수정에 활용)

    Returns:
        [SystemMessage, HumanMessage] 리스트
    """
    product_summary = json.dumps(_filter_product_info(product_info), ensure_ascii=False, indent=2)
    persona_section = f"""

## 타겟 페르소나 정보 (수정 시 반드시 반영)
{persona_info}

페르소나의 피부 고민, 가치관, 라이프스타일에 맞게 수정하세요.""" if persona_info else ""

    system_prompt = """당신은 CRM 마케팅 메시지 편집 전문가입니다.
기존 메시지를 피드백에 따라 개선하는 것이 목표입니다.

## 작성 원칙
- 기존 메시지에서 잘 된 부분은 최대한 유지하세요
- 피드백에서 지적된 부분만 수정하세요
- 제목: 40자 이내
- 본문: 350자 이내
- 상품 정보에 있는 사실만 사용하세요. 없는 수치·근거·성분은 절대 추가하지 마세요
- 과장·허위 표현 금지
- 의학적 효능 암시 금지
- 강압적 표현 금지 (예: "지금 바로!", "서두르세요!")"""

    human_prompt = f"""## 기존 메시지
제목: {existing_title}
본문: {existing_message}

## 피드백 (반드시 반영하세요)
{feedback}

## 상품 정보 (이 정보에 있는 사실만 사용)
{product_summary}

## 브랜드 톤 (준수 필수)
{brand_tone}{persona_section}"""

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]
