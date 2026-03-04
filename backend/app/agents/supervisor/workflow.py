from langgraph.graph import StateGraph, START
from .state import SupervisorState
from .nodes.supervisor_node import supervisor_node
from .nodes.search_node import search_node
from ..crm_agent.workflow import build_crm_workflow

def build_marketing_workflow(checkpointer=None):

    crm_subgraph = build_crm_workflow()

    workflow = StateGraph(SupervisorState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("crm_node", crm_subgraph)
    workflow.add_node("search_node", search_node)

    workflow.add_edge(START, "supervisor")

    return workflow.compile(checkpointer=checkpointer)