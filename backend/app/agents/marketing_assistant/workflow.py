from langgraph.graph import StateGraph, START
from langchain_core.runnables import RunnableConfig
from .state import MarketingAssistantState
from .nodes.orchestrator_node import orchestrator_node
from .nodes.recommend_product_node import recommend_product_node
from .nodes.search_node import search_node
from .nodes.crm_message_node import crm_message_node
from .nodes.quality_check_node import quality_check_node
from .nodes.message_feedback_node import message_feedback_node
from .nodes.generate_persona_node import generate_persona_node
from .nodes.bulk_persona_node import bulk_persona_node
from .nodes.product_registration_node import product_registration_node


async def init_node(state: MarketingAssistantState, config: RunnableConfig) -> dict:
    """매 요청마다 task-scope 필드를 리셋. messages는 건드리지 않음 (checkpointer가 관리)."""
    return {
        "search_queries": {},
        "recommended_products": [],
        "generated_tasks": [],
        "failed_task_ids": [],
        "feedback_retry_count": 0,
        "status": "running",
        "error": None,
        "logs": [],
    }


def build_workflow(checkpointer=None):
    workflow = StateGraph(MarketingAssistantState)

    workflow.add_node("init_node", init_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("recommend_product_node", recommend_product_node)
    workflow.add_node("search_node", search_node)
    workflow.add_node("crm_message_node", crm_message_node)
    workflow.add_node("quality_check_node", quality_check_node)
    workflow.add_node("message_feedback_node", message_feedback_node)
    workflow.add_node("generate_persona_node", generate_persona_node)
    workflow.add_node("bulk_persona_node", bulk_persona_node)
    workflow.add_node("product_registration_node", product_registration_node)

    workflow.add_edge(START, "init_node")
    workflow.add_edge("init_node", "orchestrator")

    return workflow.compile(checkpointer=checkpointer)