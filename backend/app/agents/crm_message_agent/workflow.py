from langgraph.graph import StateGraph, START, END
from ....a2a.client import A2AClient
from ...config.settings import settings
from .nodes import search_agent, supervisor_agent, make_recommend_product_node, make_generate_message_node, make_data_registration_node
from .state import CRMMessageAgentState

def build_workflow(checkpointer=None):
    recommend_client     = A2AClient(f"{settings.recommend_agent_url}/a2a/recommend-product")
    generate_client      = A2AClient(f"{settings.generate_message_agent_url}/a2a/generate-message")
    data_reg_client      = A2AClient(f"{settings.data_registration_agent_url}/a2a/data-registration")

    workflow = StateGraph(CRMMessageAgentState)

    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("search_agent", search_agent)
    workflow.add_node("recommend_product_agent", make_recommend_product_node(recommend_client))
    workflow.add_node("generate_message_agent",  make_generate_message_node(generate_client))
    workflow.add_node("data_registration_agent", make_data_registration_node(data_reg_client))

    workflow.add_edge(START, "supervisor")
    workflow.add_edge("supervisor", END)

    return workflow.compile(checkpointer=checkpointer)
