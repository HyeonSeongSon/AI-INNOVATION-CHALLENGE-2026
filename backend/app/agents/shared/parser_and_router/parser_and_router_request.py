from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from ..prompts.parse_prompt import build_crm_parse_prompt, build_generate_message_router_prompt
from ....core.logging import get_logger
from ....core.data_loader import get_categories
logger = get_logger("parse_request")

class RecommendProductRequest(BaseModel):
    """다중 값을 지원하는 상품 추천 메시지 요청"""
    persona_id: Optional[str] = Field(default=None, description="페르소나 ID (단일 값). 예: 'P123' 또는 '20대 여성'")
    product_categories: List[str] = Field(default_factory=list, description="상품 카테고리 리스트. 예: ['스킨케어', '메이크업', '헤어케어']")
    brands: List[str] = Field(default_factory=list, description="브랜드 리스트. 예: ['라네즈', '설화수', '이니스프리']")
    has_persona_info: bool = Field(default=False, description="True: 메시지에 persona_id 또는 자연어 페르소나 설명(피부타입/나이/고민 등)이 포함된 경우. False: 제품/카테고리/브랜드만 언급된 경우.")

class CRMMessageTask(BaseModel):
    """단일 상품-목적 조합"""
    product_id: str = Field(description="상품 ID. 예: 'p001'")
    purpose: Optional[str] = Field(default=None, description="메시지 목적. 예: '프로모션', '재구매유도'")


class UserFeedbackInput(BaseModel):
    """사용자 직접 피드백 입력"""
    title: str = Field(description="기존 메시지 제목")
    message: str = Field(description="기존 메시지 내용")
    product_id: str = Field(description="상품 ID (예: 'p001')")
    feedback: str = Field(description="반영할 피드백 내용")
    purpose: Optional[str] = Field(default=None, description="메시지 목적 (7가지 허용값 중 하나, 없으면 null)")


class GenerateMessageRouterResult(BaseModel):
    """인텐트 라우팅 결과 — 한 번의 LLM 호출로 의도 판단 + 노드별 데이터 추출"""
    next_node: Literal["generate_message_node", "message_feedback_node"] = Field(
        description="다음 노드. 신규 생성이면 'generate_message_node', 수정/피드백이면 'message_feedback_node'"
    )
    tasks: Optional[List[CRMMessageTask]] = Field(
        default=None,
        description="next_node == 'generate_message_node' 일 때만 채움. 생성할 메시지 태스크 목록"
    )
    feedback_input: Optional[UserFeedbackInput] = Field(
        default=None,
        description="next_node == 'message_feedback_node' 일 때만 채움. 수정 요청 데이터"
    )


async def recommend_product_parser(messages: List[AnyMessage], llm: BaseChatModel) -> Dict[str, Any]:
    """대화 메시지에서 상품 추천 조건을 LLM으로 파싱해 반환한다.

    Args:
        messages: 사용자와의 대화 메시지 목록
        llm: structured output을 지원하는 LangChain 채팅 모델
    Returns:
        RecommendProductRequest 필드(persona_id, product_categories, brands)를 담은 dict
    """
    parser = llm.with_structured_output(RecommendProductRequest)
    prompt_messages = [
        SystemMessage(content=build_crm_parse_prompt(get_categories())),
        *messages,
    ]
    try:
        response = await parser.ainvoke(prompt_messages)
        return response.model_dump()
    except Exception as e:
        logger.error("llm_parse_failed", error=str(e), exc_info=True)
        raise


async def generate_message_router(
    messages: List[AnyMessage], llm: BaseChatModel
) -> GenerateMessageRouterResult:
    """대화 메시지에서 의도를 파악해 다음 노드와 필요한 데이터를 LLM으로 추출해 반환한다.

    Args:
        messages: 사용자와의 대화 메시지 목록
        llm: structured output을 지원하는 LangChain 채팅 모델
    Returns:
        next_node(라우팅 대상)와 노드별 데이터(tasks 또는 feedback_input)를 담은 GenerateMessageRouterResult
    """
    parser = llm.with_structured_output(GenerateMessageRouterResult)
    prompt_messages = [SystemMessage(content=build_generate_message_router_prompt()), *messages]
    try:
        return await parser.ainvoke(prompt_messages)
    except Exception as e:
        logger.error("llm_parse_failed", error=str(e), exc_info=True)
        raise