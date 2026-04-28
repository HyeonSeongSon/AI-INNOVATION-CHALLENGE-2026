from ..state import MarketingAssistantState
from ....core.llm_factory import get_llm
from ....core.logging import get_logger
from ..services.orchestrator import Orchestrator
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from ....config.settings import settings

_orchestrator = Orchestrator()
logger = get_logger("orchestrator_node")

async def orchestrator_node(state: MarketingAssistantState, config: RunnableConfig):
    try:
        # fast-path: 파일 업로드 감지 → LLM 호출 없이 즉시 라우팅
        if state.get("product_file_records"):
            logger.info("orchestrator_decision", next_step="product_registration_node", reason="product_file_records detected")
            return Command(goto="product_registration_node")

        if state.get("file_records"):
            logger.info("orchestrator_decision", next_step="bulk_persona_node", reason="file_records detected")
            return Command(goto="bulk_persona_node")

        messages = state.get("messages")
        model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
        llm = get_llm(model_name, temperature=0)
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