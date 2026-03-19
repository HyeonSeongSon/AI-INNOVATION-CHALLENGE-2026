from langgraph.graph import StateGraph
from .state import MarketingAssistantState
from .nodes.recommend_product_node import recommend_product_node

def build_workflow(ckeckpointer=None):
    workflow = StateGraph(MarketingAssistantState)

    workflow.add_node("rommend_products", recommend_product_node)