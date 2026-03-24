import asyncio
from ..state import MarketingAssistantState
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from ....core.llm_factory import get_llm
from ..services.quality_check import QualityChecker
from ....config.settings import settings

_checker = QualityChecker()


async def quality_check_node(state: MarketingAssistantState, config: RunnableConfig):
    tasks = state.get("generated_tasks", [])
    model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model_name, temperature=0)

    async def check_one(task: dict) -> dict:
        result = await _checker.check_quality(
            message=task["message"],
            product_id=task["product_id"],
            purpose=task["purpose"],
            llm=llm,
        )
        return {**task, "quality_check": result}

    check_tasks = list(await asyncio.gather(*[check_one(t) for t in tasks]))
    failed_task_ids = [t["product_id"] for t in check_tasks if not t["quality_check"]["passed"]]

    return Command(
        goto="message_feedback_node" if failed_task_ids else END,
        update={
            "generated_tasks": check_tasks,
            "failed_task_ids": failed_task_ids,
        },
    )
