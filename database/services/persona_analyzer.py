"""
페르소나 LLM 분석 서비스
OpenAI API로 페르소나 요약 생성
"""

import os
import uuid
import time
import logging
from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

logger = logging.getLogger("persona_analyzer")

SYSTEM_PROMPT = """당신은 뷰티 전문가입니다.
고객의 피부 정보, 라이프스타일, 선호도를 바탕으로 해당 고객의 특성을 간결하고 명확하게 요약합니다.
요약은 3~5문장으로 작성하며, 뷰티 제품 추천에 활용될 수 있도록 핵심 특성을 담아주세요.
공란인 항목은 요약에서 제외합니다. 한국어로 작성해주세요."""


def _build_persona_description(data: Dict[str, Any]) -> str:
    lines = [
        f"이름: {data.get('name', '')}",
        f"나이: {data.get('age', '')}세, 성별: {data.get('gender', '')}, 직업: {data.get('occupation', '')}",
        f"피부 타입: {', '.join(data.get('skin_type', []))}",
        f"피부 고민: {', '.join(data.get('skin_concerns', []))}",
        f"퍼스널 컬러: {data.get('personal_color', '')}, 쉐이드 번호: {data.get('shade_number', '')}",
        f"선호 색상: {', '.join(data.get('preferred_colors', []))}",
        f"선호 성분: {', '.join(data.get('preferred_ingredients', []))}",
        f"기피 성분: {', '.join(data.get('avoided_ingredients', []))}",
        f"선호 향: {', '.join(data.get('preferred_scents', []))}",
        f"가치관: {', '.join(data.get('values', []))}",
        f"스킨케어 루틴: {data.get('skincare_routine', '')}",
        f"주 활동 환경: {data.get('main_environment', '')}",
        f"선호 제형: {', '.join(data.get('preferred_texture', []) if isinstance(data.get('preferred_texture'), list) else ([data.get('preferred_texture')] if data.get('preferred_texture') else []))}",
        f"반려동물: {data.get('pets', '')}",
        f"평균 수면: {data.get('avg_sleep_hours', '')}시간, 스트레스: {data.get('stress_level', '')}",
        f"디지털 기기 사용: {data.get('digital_device_usage_time', '')}시간/일",
        f"쇼핑 스타일: {data.get('shopping_style', '')}",
        f"구매 결정 요인: {', '.join(data.get('purchase_decision_factors', []) if isinstance(data.get('purchase_decision_factors'), list) else ([data.get('purchase_decision_factors')] if data.get('purchase_decision_factors') else []))}",
    ]
    return "\n".join(line for line in lines if line.split(": ", 1)[-1].strip())


async def generate_persona_summary(persona_data: Dict[str, Any], model: str = None) -> Tuple[str, str]:
    """
    LLM으로 페르소나 요약 생성

    Returns:
        (persona_id, persona_summary)
    """
    model_name = model or os.getenv("CHATGPT_MODEL_NAME", "gpt-4o-mini")
    persona_name = persona_data.get("name", "unknown")

    logger.info("persona_summary_started | persona_name=%s model=%s", persona_name, model_name)
    start = time.perf_counter()

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    description = _build_persona_description(persona_data)
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"다음 고객 정보를 요약해주세요:\n\n{description}"},
            ],
        )
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.error("persona_summary_llm_failed | persona_name=%s model=%s duration_ms=%s error=%s",
                     persona_name, model_name, duration_ms, str(e), exc_info=True)
        raise

    summary = response.choices[0].message.content.strip()
    persona_id = f"PERSONA_{uuid.uuid4().hex[:12].upper()}"

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info("persona_summary_completed | persona_name=%s persona_id=%s model=%s duration_ms=%s",
                persona_name, persona_id, model_name, duration_ms)

    return persona_id, summary
