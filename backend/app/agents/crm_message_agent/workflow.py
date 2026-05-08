from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph

from .nodes import search_agent, supervisor_agent, recommend_product_agent, generate_message_agent
from .state import CRMMessageAgentState

def build_workflow(checkpointer=None):
    workflow = StateGraph(CRMMessageAgentState)

    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("search_agent", search_agent)
    workflow.add_node("recommend_product_agent", recommend_product_agent)
    workflow.add_node("generate_message_agent", generate_message_agent)

    return workflow.compile(checkpointer=checkpointer)
