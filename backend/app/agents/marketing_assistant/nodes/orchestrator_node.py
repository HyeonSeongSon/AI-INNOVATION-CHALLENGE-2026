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
        from langchain_core.messages import SystemMessage as _SystemMessage
        messages = list(state.get("messages") or [])

        # 파일 첨부 여부를 시스템 메시지로 LLM에게 전달
        if state.get("file_records"):
            messages = [_SystemMessage(content="[파일 첨부됨] 사용자가 파일을 업로드했습니다.")] + messages

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