from ..state import MarketingAssistantState
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from ....core.llm_factory import get_llm
from ..services.apply_feedback import get_applier
from ..services.parse_request import MultiValueParser
from ..services.product_client import ProductClient
from ....config.settings import settings

_MAX_RETRIES = 2
_DEFAULT_PURPOSE = "브랜드/제품 첫소개"

_parser = MultiValueParser()
_product_client = ProductClient()


async def message_feedback_node(state: MarketingAssistantState, config: RunnableConfig):
    retry_count = state.get("feedback_retry_count", 0)

    if retry_count >= _MAX_RETRIES:
        return Command(goto=END, update={"feedback_retry_count": 0})

    failed_ids = set(state.get("failed_task_ids", []))
    model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model_name, temperature=0.5)

    if not failed_ids:
        # 사용자 직접 피드백 분기 (오케스트레이터에서 진입)
        messages = state["messages"]
        parser_llm = get_llm(settings.parser_model_name, temperature=0)
        parsed = await _parser.user_feedback_parser(messages, parser_llm)

        # 상품 정보 조회 -> brand 추출
        product_info = await _product_client.get_merged_product_info(parsed["product_id"])
        brand = product_info.get("brand", "")

        # 기존 generated_tasks에서 purpose 보조 조회 (사용자가 명시하지 않은 경우)
        existing_tasks = state.get("generated_tasks", [])
        existing = next((t for t in existing_tasks if t.get("product_id") == parsed["product_id"]), None)
        purpose = parsed.get("purpose") or (existing or {}).get("purpose") or _DEFAULT_PURPOSE

        task = {
            "product_id": parsed["product_id"],
            "purpose": purpose,
            "brand": brand,
            "message": {"title": parsed["title"], "message": parsed["message"]},
            "quality_check": {
                "passed": False,
                "failed_stage": "user_feedback",
                "failure_reason": parsed["feedback"],
                "llm_judge_scores": {"feedback": parsed["feedback"]},
            },
        }
        updated_task = await get_applier().apply_feedback(task, llm)
        return Command(
            goto="quality_check_node",
            update={
                "generated_tasks": [updated_task],
                "failed_task_ids": [],
                "feedback_retry_count": 0,
            },
        )

    # 기존: quality_check 실패 분기
    tasks = state.get("generated_tasks", [])
    updated_tasks = await get_applier().apply_feedback_batch(tasks, failed_ids, llm)

    return Command(
        goto="quality_check_node",
        update={
            "generated_tasks": updated_tasks,
            "failed_task_ids": [],
            "feedback_retry_count": retry_count + 1,
        },
    )
