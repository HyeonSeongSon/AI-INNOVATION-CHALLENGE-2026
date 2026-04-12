from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field
from ..prompts.generate_query_prompt import build_persona_structured_prompt, build_generate_query_prompt
import json


class PersonaData(BaseModel):
    name: str = Field(description="페르소나 이름. 실명이 있으면 그대로, 없으면 핵심 특징을 담은 간단한 설명으로 대체 (예: 트러블 관리가 중요한 20대 대학생)")
    gender: Optional[str] = Field(default=None, description="성별 (예: 여성, 남성)")
    age: Optional[int] = Field(default=None, description="나이")
    occupation: Optional[str] = Field(default=None, description="직업 (예: 직장인, 대학생)")
    skin_type: List[str] = Field(default_factory=list, description="피부 타입 (예: 지성, 복합성, 건성)")
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


async def generate_structured_persona_info(user_input: str, llm) -> Dict:
    structured_llm = llm.with_structured_output(PersonaData)
    prompt = build_persona_structured_prompt(user_input)
    result = await structured_llm.ainvoke(prompt)
    return result.model_dump()

async def generate_search_query(persona_info: Union[Dict, str], llm) -> Dict:
    prompt = build_generate_query_prompt(persona_info)
    generate_query_response = await llm.ainvoke(prompt)
    search_query = json.loads(generate_query_response.content)
    return search_query
