
from ..state import MarketingAssistantState
from ....core.llm_factory import get_llm
from ....core.logging import get_logger
from ..services.orchestrator import Orchestrator
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.constants import END
from ....config.settings import settings

import os

_orchestrator = Orchestrator()
logger = get_logger("orchestrator_node")

async def orchestrator_node(state: MarketingAssistantState, config: RunnableConfig):
    try:
        messages = state.get("messages")
        llm = get_llm(settings.chatgpt_model_name, temperature=0)
        decision = await _orchestrator.orchestrator(messages, llm)

        logger.info(
            "orchestrator_decision",
            next_step=decision.next_step,
            reason=decision.reason,
        )
        return Command(goto=decision.next_step)
    except Exception as e:
        logger.error(
            "supervisor_node_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise