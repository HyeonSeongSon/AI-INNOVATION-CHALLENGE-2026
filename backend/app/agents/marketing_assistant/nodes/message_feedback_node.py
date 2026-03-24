from ..state import MarketingAssistantState
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from ....core.llm_factory import get_llm
from ..services.apply_feedback import get_applier
from ....config.settings import settings

_MAX_RETRIES = 2


async def message_feedback_node(state: MarketingAssistantState, config: RunnableConfig):
    retry_count = state.get("feedback_retry_count", 0)

    if retry_count >= _MAX_RETRIES:
        return Command(goto=END, update={"feedback_retry_count": 0})

    tasks = state.get("generated_tasks", [])
    failed_ids = set(state.get("failed_task_ids", []))

    model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model_name, temperature=0.5)

    updated_tasks = await get_applier().apply_feedback_batch(tasks, failed_ids, llm)

    return Command(
        goto="quality_check_node",
        update={
            "generated_tasks": updated_tasks,
            "failed_task_ids": [],
            "feedback_retry_count": retry_count + 1,
        },
    )
