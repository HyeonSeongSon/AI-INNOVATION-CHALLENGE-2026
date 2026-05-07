from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from ..prompts.generate_query_prompt import build_persona_structured_prompt, build_generate_query_prompt
import json

from app.core.logging import get_logger

logger = get_logger("generate_persona_and_query")


class PersonaData(BaseModel):
    name: str = Field(description="페르소나 이름. 실명이 있으면 그대로, 없으면 핵심 특징을 담은 간단한 설명으로 대체 (예: XX세 성별 직업")
    gender: Optional[str] = Field(default=None, description="성별 (예: 여성, 남성)")
    age: Optional[int] = Field(default=None, description="나이")
    occupation: Optional[str] = Field(default=None, description="직업 (예: 직장인, 대학생)")
    skin_type: List[str] = Field(default_factory=list, description="피부 타입 키워드만. 반드시 표준 단어로 제한. 올바른 예: ['건성'], ['지성'], ['복합성'], ['민감성'], ['건성', '민감성']. 절대 금지: 서술형 문장, 증상 설명, 괄호 부연설명 (잘못된 예: '샤워 후 당기는 건성', '복합성(T존 번들거림)')")
    concerns: List[str] = Field(default_factory=list, description="피부·헤어 고민 키워드만. 반드시 표준 단어 하나씩 나열. 올바른 예: ['잡티', '붉은기', '건조', '트러블', '모공', '여드름', '탈모', '두피 지성']. 절대 금지: 서술형 문장, 상황 설명, 원인 서술 (잘못된 예: '컨디션에 따라 트러블 올라옴', '피지 분비 많은 편')")
    personal_color: Optional[str] = Field(default=None, description="퍼스널 컬러 (예: 웜톤, 쿨톤, 봄웜)")
    shade_number: Optional[int] = Field(default=None, description="파운데이션 쉐이드 번호 (예: 21, 23, 25)")
    preferred_colors: List[str] = Field(default_factory=list, description="선호 색상 (예: 누드, 코랄, 레드)")
    preferred_ingredients: List[str] = Field(default_factory=list, description="선호 성분 (예: 히알루론산, 나이아신아마이드)")
    avoided_ingredients: List[str] = Field(default_factory=list, description="기피 성분 (예: 알코올, 향료, 파라벤)")
    preferred_scents: List[str] = Field(default_factory=list, description="선호 향 (예: 무향, 플로럴, 시트러스)")
    lifestyle_values: List[str] = Field(default_factory=list, description="가치관/추구 키워드만. 반드시 단어 단위로 나열. 올바른 예: ['비건', '친환경', '가성비', '미니멀리즘']. 절대 금지: 서술형 문장 (잘못된 예: '친환경적인 삶을 중요하게 생각하는')")
    skincare_routine: List[str] = Field(default_factory=list, description="스킨케어 루틴 유형 키워드만. 올바른 예: ['미니멀', '풀루틴', '기초케어중심']. 절대 금지: 서술형 문장 (잘못된 예: '아침저녁으로 꼼꼼히 루틴을 지키는 편')")
    main_environment: List[str] = Field(default_factory=list, description="주요 생활환경 (예: 실내사무실, 야외활동)")
    preferred_texture: List[str] = Field(default_factory=list, description="선호 텍스처 키워드만. 반드시 짧은 형용사/명사 단위로 나열. 올바른 예: ['가벼운', '촉촉한', '매트', '흡수빠른']. 절대 금지: 서술형 문장 (잘못된 예: '가볍고 흡수가 빠른 텍스처를 선호')")
    hair_type: List[str] = Field(default_factory=list, description="헤어 타입 키워드만. 반드시 표준 단어로 변환. 올바른 예: ['직모', '곱슬', '손상모', '가는모발', '굵은모발']. 절대 금지: 서술형 문장 (잘못된 예: '열 손상으로 푸석해진 모발')")
    beauty_interests: List[str] = Field(default_factory=list, description="관심 뷰티 카테고리 (예: 스킨케어, 메이크업, 헤어, 바디케어)")
    pets: List[str] = Field(default_factory=list, description="반려동물 (예: 고양이, 강아지)")
    avg_sleep_hours: Optional[int] = Field(default=None, description="평균 수면 시간 (시간 단위)")
    stress_level: Optional[str] = Field(default=None, description="스트레스 수준 (예: 높음, 보통, 낮음)")
    daily_screen_hours: Optional[int] = Field(default=None, description="하루 스크린 사용 시간 (시간 단위)")
    shopping_style: List[str] = Field(default_factory=list, description="쇼핑 스타일 키워드만. 올바른 예: ['충동구매', '계획구매', '리뷰중시', '신중구매']. 절대 금지: 서술형 문장 (잘못된 예: '리뷰를 꼼꼼히 읽고 신중하게 구매하는 편')")
    purchase_decision_factors: List[str] = Field(default_factory=list, description="구매 결정 요인 (예: 성분, 가격, 브랜드, 리뷰)")
    price_sensitivity: Optional[str] = Field(default=None, description="가격 민감도 (예: 가성비중시, 프리미엄선호, 무관)")
    preferred_brands: List[str] = Field(default_factory=list, description="선호 브랜드 (예: 설화수, 이니스프리)")
    avoided_brands: List[str] = Field(default_factory=list, description="기피 브랜드")
    persona_summary: Optional[str] = Field(default=None, description="페르소나 전반을 자연스럽게 요약한 설명문")


async def generate_structured_persona_info(messages: List, llm) -> Dict:
    """
    멀티턴 대화를 분석하여 구조화된 페르소나 정보를 생성.

    모든 사용자 발화를 종합해 PersonaData 스키마에 맞는 페르소나를 추출.
    명시되지 않은 필드는 추론하지 않고 null/빈 배열로 둡니다.

    Args:
        messages: LangChain 메시지 리스트 (HumanMessage, AIMessage 등)
        llm: structured output을 지원하는 LangChain LLM 인스턴스

    Returns:
        PersonaData 스키마를 따르는 딕셔너리
    """
    logger.info("generate_structured_persona_info_started", message_count=len(messages))
    structured_llm = llm.with_structured_output(PersonaData)
    prompt_messages = [SystemMessage(content=build_persona_structured_prompt()), *messages]
    result = await structured_llm.ainvoke(prompt_messages)
    persona = result.model_dump()
    logger.info(
        "generate_structured_persona_info_completed",
        persona_name=persona.get("name"),
        skin_type=persona.get("skin_type"),
        concerns=persona.get("concerns"),
    )
    return persona


async def generate_search_query(messages: List, llm) -> Dict:
    """
    멀티턴 대화를 바탕으로 상품 검색에 사용할 쿼리를 생성.

    구조화된 데이터가 아닌 사용자 발화 원문을 그대로 사용하며,
    모든 턴의 발화를 종합해 검색 쿼리를 생성합니다.

    Args:
        messages: LangChain 메시지 리스트 (HumanMessage, AIMessage 등)
        llm: LangChain LLM 인스턴스

    Returns:
        검색 쿼리를 담은 딕셔너리 {"need", "preference", "retrieval", "persona"}
    """
    logger.info("generate_search_query_started", message_count=len(messages))
    prompt_messages = [SystemMessage(content=build_generate_query_prompt()), *messages]
    response = await llm.ainvoke(prompt_messages)
    search_query = json.loads(response.content)
    logger.info(
        "generate_search_query_completed",
        query_keys=list(search_query.keys()) if isinstance(search_query, dict) else None,
    )
    return search_query
