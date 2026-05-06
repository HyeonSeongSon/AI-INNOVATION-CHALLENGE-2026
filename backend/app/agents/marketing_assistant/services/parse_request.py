from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from ..prompts.parse_prompt import build_crm_parse_prompt, build_crm_message_parse_prompt, build_user_feedback_parse_prompt
from ....core.logging import get_logger
from ....core.data_loader import get_categories
import json

logger = get_logger("parse_request")

class RecommendProductRequest(BaseModel):
    """다중 값을 지원하는 상품 추천 메시지 요청"""

    persona_id: Optional[str] = Field(
        default=None,
        description="페르소나 ID (단일 값). 예: 'P123' 또는 '20대 여성'"
    )

    product_categories: List[str] = Field(
        default_factory=list,
        description="상품 카테고리 리스트. 예: ['스킨케어', '메이크업', '헤어케어']"
    )

    brands: List[str] = Field(
        default_factory=list,
        description="브랜드 리스트. 예: ['라네즈', '설화수', '이니스프리']"
    )

class CRMMessageTask(BaseModel):
    """단일 상품-목적 조합"""
    product_id: str = Field(description="상품 ID. 예: 'p001'")
    purpose: Optional[str] = Field(default=None, description="메시지 목적. 예: '프로모션', '재구매유도'")


class CRMMessageParseResult(BaseModel):
    """CRM 메시지 파싱 결과 — 여러 상품이 언급된 경우 각각 별도 task"""
    tasks: List[CRMMessageTask] = Field(default_factory=list)


class UserFeedbackInput(BaseModel):
    """사용자 직접 피드백 입력 — 오케스트레이터에서 message_feedback_node로 진입 시 파싱"""
    title: str = Field(description="기존 메시지 제목")
    message: str = Field(description="기존 메시지 내용")
    product_id: str = Field(description="상품 ID (예: 'p001')")
    feedback: str = Field(description="반영할 피드백 내용")
    purpose: Optional[str] = Field(default=None, description="메시지 목적 (7가지 허용값 중 하나, 없으면 null)")


class MultiValueParser:
    def __init__(self):
        logger.info("parser_initialized")

    async def recommend_product_parser(self, messages: List[AnyMessage], llm: BaseChatModel) -> str:
        """대화 히스토리 → 다중 값 파싱

        마지막 사용자 메시지만이 아니라 전체 대화 히스토리를 전달하여
        이전 AI 메시지에 포함된 persona_id도 추출할 수 있도록 합니다.

        Args:
            messages: 전체 대화 메시지 리스트 (HumanMessage/AIMessage)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)
        """
        parser = llm.with_structured_output(RecommendProductRequest)
        prompt_messages = [
            SystemMessage(content=build_crm_parse_prompt(get_categories())),
            *messages,
        ]
        try:
            response = await parser.ainvoke(prompt_messages)
            return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            return json.dumps({"error": f"파싱 중 오류 발생: {str(e)}"}, ensure_ascii=False)
        
    async def crm_message_parser(self, messages: List[AnyMessage], llm: BaseChatModel) -> List[Dict[str, Any]]:
        """대화 이력 → product_id/purpose 파싱.

        마지막 메시지가 단순 재시도("다시 만들어줘" 등)인 경우
        이전 대화 맥락에서 product_id/purpose를 추출합니다.

        Args:
            messages: 전체 대화 메시지 리스트 (HumanMessage/AIMessage)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)
        """
        parser = llm.with_structured_output(CRMMessageParseResult)
        prompt_messages = [SystemMessage(content=build_crm_message_parse_prompt()), *messages]
        try:
            response = await parser.ainvoke(prompt_messages)
            return [t.model_dump() for t in response.tasks]
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            raise

    async def user_feedback_parser(self, messages: List[AnyMessage], llm: BaseChatModel) -> Dict[str, Any]:
        """사용자 직접 피드백 입력 파싱 — 대화 히스토리에서 title, message, product_id, feedback, purpose 추출.

        Args:
            messages: 전체 대화 메시지 리스트 (AIMessage에 기존 CRM 내용 포함)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)

        Returns:
            UserFeedbackInput 필드로 구성된 dict
        """
        parser = llm.with_structured_output(UserFeedbackInput)
        prompt_messages = [SystemMessage(content=build_user_feedback_parse_prompt()), *messages]
        try:
            response = await parser.ainvoke(prompt_messages)
            return response.model_dump()
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            raise