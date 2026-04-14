"""
페르소나 생성 서비스
자유 텍스트 → 구조화된 페르소나 정보 + 검색 쿼리 생성
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

logger = logging.getLogger("persona_creator")


class PersonaData(BaseModel):
    name: str = Field(description="페르소나 이름. 실명이 있으면 그대로, 없으면 핵심 특징을 담은 간단한 설명으로 대체 (예: 트러블 관리가 중요한 20대 대학생)")
    gender: Optional[str] = Field(default=None, description="성별 (예: 여성, 남성)")
    age: Optional[int] = Field(default=None, description="나이")
    occupation: Optional[str] = Field(default=None, description="직업 (예: 직장인, 대학생)")
    skin_type: List[str] = Field(default_factory=list, description="피부 타입 (예: 지성, 복합성, 건성), 피부 타입 외 작성 금지(예: 복합성(T존 번들거림))")
    skin_concerns: List[str] = Field(default_factory=list, description="피부 고민 (예: 모공, 여드름, 색소침착)")
    personal_color: Optional[str] = Field(default=None, description="퍼스널 컬러 (예: 웜톤, 쿨톤, 봄웜)")
    shade_number: Optional[int] = Field(default=None, description="파운데이션 쉐이드 번호 (예: 21, 23, 25)")
    preferred_colors: List[str] = Field(default_factory=list, description="선호 색상 (예: 누드, 코럴, 레드)")
    preferred_ingredients: List[str] = Field(default_factory=list, description="선호 성분 (예: 히알루론산, 나이아신아마이드)")
    avoided_ingredients: List[str] = Field(default_factory=list, description="기피 성분 (예: 알코올, 향료, 파라벤)")
    preferred_scents: List[str] = Field(default_factory=list, description="선호 향 (예: 무향, 플로럴, 시트러스)")
    values: List[str] = Field(default_factory=list, description="가치관/추구 (예: 비건, 친환경, 가성비)")
    skincare_routine: Optional[str] = Field(default=None, description="스킨케어 루틴 유형 (예: 미니멀, 풀루틴)")
    main_environment: Optional[str] = Field(default=None, description="주요 생활환경 (예: 실내사무실, 야외활동)")
    preferred_texture: List[str] = Field(default_factory=list, description="선호 텍스처 (예: 가벼운, 촉촉한, 매트)")
    pets: Optional[str] = Field(default=None, description="반려동물 (예: 없음, 고양이, 강아지)")
    avg_sleep_hours: Optional[int] = Field(default=None, description="평균 수면 시간 (시간 단위)")
    stress_level: Optional[str] = Field(default=None, description="스트레스 수준 (예: 높음, 보통, 낮음)")
    digital_device_usage_time: Optional[int] = Field(default=None, description="하루 디지털 기기 사용 시간 (시간 단위)")
    shopping_style: Optional[str] = Field(default=None, description="쇼핑 스타일 (예: 충동구매, 계획구매, 리뷰중시)")
    purchase_decision_factors: List[str] = Field(default_factory=list, description="구매 결정 요인 (예: 성분, 가격, 브랜드, 리뷰)")
    persona_summary: Optional[str] = Field(default=None, description="페르소나 전반을 자연스럽게 요약한 설명문")


def _get_llm(model_name: str = None) -> ChatOpenAI:
    model = model_name or os.getenv("CHATGPT_MODEL_NAME", "gpt-5-mini")
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


async def generate_structured_persona_info(user_input: str, model_name: str = None) -> Dict[str, Any]:
    """
    자유 텍스트를 구조화된 페르소나 정보로 변환.

    Args:
        user_input: 페르소나를 생성할 원본 사용자 입력 텍스트
        model_name: 사용할 LLM 모델명 (없으면 환경변수에서 읽음)

    Returns:
        PersonaData 스키마를 따르는 딕셔너리
    """
    llm = _get_llm(model_name)
    logger.info("generate_structured_persona_info_started | input_length=%d model=%s", len(user_input), llm.model_name)

    structured_llm = llm.with_structured_output(PersonaData)
    prompt = f"""사용자 입력을 바탕으로 뷰티 상품 추천용 페르소나 정보를 구조화해서 추출하세요.
명시되지 않은 필드는 입력 맥락에서 합리적으로 추론하거나, 추론이 불가능하면 null/빈 배열로 두세요.
persona_summary는 페르소나 전반을 2~3문장으로 자연스럽게 요약하세요.

사용자 입력:
{user_input}
"""
    result = await structured_llm.ainvoke(prompt)
    persona = result.model_dump()
    logger.info(
        "generate_structured_persona_info_completed | persona_name=%s skin_type=%s",
        persona.get("name"),
        persona.get("skin_type"),
    )
    return persona


_SEARCH_QUERY_PROMPT_TEMPLATE = """
당신은 뷰티·라이프스타일 상품 추천 시스템용 검색 쿼리 생성 전문가입니다.
주어진 페르소나를 깊이 이해하고, 이 사용자에게 실제로 맞는 상품을 찾기 위한
검색/매칭용 4개 쿼리(need / preference / retrieval / persona)를 생성하세요.

[쿼리 역할]
- need: 사용자가 원하는 결과 상태 (자연스러운 문장형)
- preference: 선호하는 제품 속성/사용감/스타일 (자연스러운 문장형)
- retrieval: 검색창에 입력할 법한 짧고 응집된 검색 문구
- persona: 이 상품이 필요한 사람 유형 묘사 (자연스러운 문장형, 추천 문장 금지)

반드시 아래 JSON 형식만 반환하세요:
{{
  "need": "",
  "preference": "",
  "retrieval": "",
  "persona": ""
}}

Persona:
{persona_str}
"""


async def generate_search_query(persona_info: Union[Dict[str, Any], str], model_name: str = None) -> Dict[str, str]:
    """
    페르소나 정보를 기반으로 상품 검색 쿼리 생성.

    Args:
        persona_info: 구조화된 페르소나 정보 딕셔너리 또는 문자열
        model_name: 사용할 LLM 모델명 (없으면 환경변수에서 읽음)

    Returns:
        {"need": ..., "preference": ..., "retrieval": ..., "persona": ...}
    """
    llm = _get_llm(model_name)
    persona_str = json.dumps(persona_info, ensure_ascii=False, indent=2) if isinstance(persona_info, dict) else persona_info
    persona_name = persona_info.get("name") if isinstance(persona_info, dict) else None
    logger.info("generate_search_query_started | persona_name=%s model=%s", persona_name, llm.model_name)

    prompt = _SEARCH_QUERY_PROMPT_TEMPLATE.format(persona_str=persona_str)
    response = await llm.ainvoke(prompt)
    search_query = json.loads(response.content)
    logger.info(
        "generate_search_query_completed | persona_name=%s query_keys=%s",
        persona_name,
        list(search_query.keys()),
    )
    return search_query
