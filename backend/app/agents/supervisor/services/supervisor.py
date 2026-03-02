from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from ....core.logging import get_logger
from ..prompts.supervisor_prompt import build_supervisor_prompt

logger = get_logger("supervisor")

class RouteResponse(BaseModel):
    next_step: Literal["crm_node", "search_node", "FINISH"] = Field(
        description = "다음 작업을 수행할 노드를 선택하거나 모든작업이 완료되었으면 FINISH를 선택"
    )
    reason: str = Field(description="선택한 이유")

class Supervisor:
    def __init__(self):
        logger.info("supervisor_initialized")

    async def supervisor(self, messages, llm: BaseChatModel):
        supervisor_agent = llm.with_structured_output(RouteResponse)
        prompt_messages = build_supervisor_prompt(messages)
        response = supervisor_agent.ainvoke(prompt_messages)
        return await response