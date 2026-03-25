from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from ..prompts.parse_prompt import build_crm_parse_prompt, build_crm_message_parse_prompt, build_user_feedback_parse_prompt
from ....core.logging import get_logger
from ....core.data_loader import get_categories
import json

logger = get_logger("parse_crm_request")

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

    async def recommend_product_parser(self, user_input: str, llm: BaseChatModel) -> str:
        """자연어 → 다중 값 파싱

        Args:
            user_input: 사용자 입력 (자연어 또는 JSON)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)
        """
        parser = llm.with_structured_output(RecommendProductRequest)
        messages = [
            SystemMessage(content=build_crm_parse_prompt(get_categories())),
            HumanMessage(content=user_input)
        ]
        try:
            response = await parser.ainvoke(messages)
            return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            return json.dumps({"error": f"파싱 중 오류 발생: {str(e)}"}, ensure_ascii=False)
        
    async def crm_message_parser(self, user_input: str, llm: BaseChatModel) -> List[Dict[str, Any]]:
        """자연어 → product_id/purpose 파싱. 여러 상품이 언급된 경우 parallel 플래그와 함께 반환.

        Args:
            user_input: 사용자 입력 (자연어 또는 JSON)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)

        Returns:
            JSON 문자열. 예:
            단일: {"parallel": false, "tasks": [{"product_id": "p001", "purpose": "프로모션"}]}
            복수: {"parallel": true,  "tasks": [{"product_id": "p001", ...}, {"product_id": "p002", ...}]}
        """
        parser = llm.with_structured_output(CRMMessageParseResult)
        messages = [
            SystemMessage(content=build_crm_message_parse_prompt()),
            HumanMessage(content=user_input)
        ]
        try:
            response = await parser.ainvoke(messages)
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