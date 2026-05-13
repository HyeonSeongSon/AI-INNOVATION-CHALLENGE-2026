from langgraph.graph import StateGraph, START, END

from .state import DataRegistrationState
from .nodes import init_node, data_registration_agent_node


def build_workflow(checkpointer=None):
    workflow = StateGraph(DataRegistrationState)

    workflow.add_node("init_node", init_node)
    workflow.add_node("data_registration_agent", data_registration_agent_node)

    workflow.add_edge(START, "init_node")
    workflow.add_edge("init_node", "data_registration_agent")
    workflow.add_edge("data_registration_agent", END)

    return workflow.compile(checkpointer=checkpointer)

graph = build_workflow()
