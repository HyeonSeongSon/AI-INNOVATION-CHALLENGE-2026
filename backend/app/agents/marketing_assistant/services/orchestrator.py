from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from ....core.logging import get_logger
from ..prompts.orchestrator_prompt import build_orchestrator_prompt

logger = get_logger("orchestrator")

class RouteResponse(BaseModel):
    next_step: Literal["recommend_product_node", "crm_message_node", "search_node", "message_feedback_node", "generate_persona_node"] = Field(
        description = "다음 작업을 수행할 노드를 선택"
    )
    reason: str = Field(description="선택한 이유")

class Orchestrator:
    def __init__(self):
        logger.info("orchestrator_initialized")

    async def orchestrator(self, messages, llm: BaseChatModel):
        supervisor = llm.with_structured_output(RouteResponse)
        prompt_messages = build_orchestrator_prompt(messages)
        response = supervisor.ainvoke(prompt_messages)
        return await response