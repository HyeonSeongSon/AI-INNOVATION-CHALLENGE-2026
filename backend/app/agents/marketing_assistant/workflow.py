from langgraph.graph import StateGraph, START
from .state import MarketingAssistantState
from .nodes.orchestrator_node import orchestrator_node
from .nodes.recommend_product_node import recommend_product_node
from .nodes.search_node import search_node
from .nodes.crm_message_node import crm_message_node
from .nodes.quality_check_node import quality_check_node
from .nodes.message_feedback_node import message_feedback_node

def build_workflow(checkpointer=None):
    workflow = StateGraph(MarketingAssistantState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("recommend_product_node", recommend_product_node)
    workflow.add_node("search_node", search_node)
    workflow.add_node("crm_message_node", crm_message_node)
    workflow.add_node("quality_check_node", quality_check_node)
    workflow.add_node("message_feedback_node", message_feedback_node)

    workflow.add_edge(START, "orchestrator")

    return workflow.compile(checkpointer=checkpointer)