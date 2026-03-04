"""
페르소나 분석 서비스
LLM으로 페르소나 요약 생성 후 Database API에 저장
"""

import os
import uuid
import httpx
from typing import Any, Dict

from ..core.logging import get_logger
from ..core.llm_factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

logger = get_logger("persona_analyzer")

SYSTEM_PROMPT = """당신은 뷰티 전문가입니다.
고객의 피부 정보, 라이프스타일, 선호도를 바탕으로 해당 고객의 특성을 간결하고 명확하게 요약합니다.
요약은 3~5문장으로 작성하며, 뷰티 제품 추천에 활용될 수 있도록 핵심 특성을 담아주세요.
한국어로 작성해주세요."""


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
        f"선호 제형: {', '.join(data.get('preferred_texture', []) if isinstance(data.get('preferred_texture'), list) else [data.get('preferred_texture', '')])}",
        f"반려동물: {data.get('pets', '')}",
        f"평균 수면: {data.get('avg_sleep_hours', '')}시간, 스트레스: {data.get('stress_level', '')}",
        f"디지털 기기 사용: {data.get('digital_device_usage_time', '')}시간/일",
        f"쇼핑 스타일: {data.get('shopping_style', '')}",
        f"구매 결정 요인: {', '.join(data.get('purchase_decision_factors', []) if isinstance(data.get('purchase_decision_factors'), list) else [data.get('purchase_decision_factors', '')])}",
    ]
    return "\n".join(line for line in lines if line.split(": ", 1)[-1].strip())


async def analyze_and_save_persona(persona_data: Dict[str, Any], model: str = None) -> Dict[str, Any]:
    """
    1. LLM으로 페르소나 요약 생성
    2. Database API에 페르소나 저장
    3. 결과 반환
    """
    model_name = model or os.getenv("CHATGPT_MODEL_NAME", "gpt-4o-mini")
    db_api_url = os.getenv("DATABASE_API_URL", "http://localhost:8020")

    # 1. LLM 요약 생성
    logger.info("persona_analysis_start", name=persona_data.get("name"))

    llm = get_llm(model_name, temperature=0.3)
    description = _build_persona_description(persona_data)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"다음 고객 정보를 요약해주세요:\n\n{description}"),
    ]
    response = await llm.ainvoke(messages)
    persona_summary = response.content.strip()

    logger.info("persona_analysis_done", name=persona_data.get("name"))

    # 2. persona_id 생성
    persona_id = f"PERSONA_{uuid.uuid4().hex[:12].upper()}"

    # 3. preferred_texture를 list로 정규화
    preferred_texture = persona_data.get("preferred_texture", [])
    if isinstance(preferred_texture, str):
        preferred_texture = [preferred_texture] if preferred_texture else []

    # 4. purchase_decision_factors를 list로 정규화
    purchase_decision_factors = persona_data.get("purchase_decision_factors", [])
    if isinstance(purchase_decision_factors, str):
        purchase_decision_factors = [purchase_decision_factors] if purchase_decision_factors else []

    # 5. Database API에 저장
    payload = {
        "persona_id": persona_id,
        "name": persona_data.get("name"),
        "gender": persona_data.get("gender"),
        "age": persona_data.get("age"),
        "occupation": persona_data.get("occupation"),
        "skin_type": persona_data.get("skin_type", []),
        "skin_concerns": persona_data.get("skin_concerns", []),
        "personal_color": persona_data.get("personal_color"),
        "shade_number": persona_data.get("shade_number"),
        "preferred_colors": persona_data.get("preferred_colors", []),
        "preferred_ingredients": persona_data.get("preferred_ingredients", []),
        "avoided_ingredients": persona_data.get("avoided_ingredients", []),
        "preferred_scents": persona_data.get("preferred_scents", []),
        "values": persona_data.get("values", []),
        "skincare_routine": persona_data.get("skincare_routine"),
        "main_environment": persona_data.get("main_environment"),
        "preferred_texture": preferred_texture,
        "pets": persona_data.get("pets"),
        "avg_sleep_hours": persona_data.get("avg_sleep_hours"),
        "stress_level": persona_data.get("stress_level"),
        "digital_device_usage_time": persona_data.get("digital_device_usage_time"),
        "shopping_style": persona_data.get("shopping_style"),
        "purchase_decision_factors": purchase_decision_factors,
        "persona_summary": persona_summary,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{db_api_url}/api/personas", json=payload)
        if resp.status_code != 200:
            logger.error("db_save_failed", status=resp.status_code, body=resp.text)
            raise RuntimeError(f"DB 저장 실패: {resp.status_code} {resp.text}")

    logger.info("persona_saved", persona_id=persona_id)

    return {
        "persona_id": persona_id,
        "persona_summary": persona_summary,
    }
