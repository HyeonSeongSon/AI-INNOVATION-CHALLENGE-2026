from langgraph.graph import StateGraph, START, END
from ..recommend_product_agent.workflow import build_workflow as build_recommend_workflow
from ..generate_message_agent.workflow import build_workflow as build_generate_message_workflow
from ..data_registration_agent.workflow import build_workflow as build_data_registration_workflow
from .nodes import search_agent, supervisor_agent, make_recommend_product_node, make_generate_message_node, make_data_registration_node
from .state import CRMMessageAgentState

def build_workflow(checkpointer=None):
    recommend_graph = build_recommend_workflow(checkpointer=checkpointer)
    generate_message_graph = build_generate_message_workflow(checkpointer=checkpointer)
    data_registration_graph = build_data_registration_workflow(checkpointer=checkpointer)

    workflow = StateGraph(CRMMessageAgentState)

    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("search_agent", search_agent)
    workflow.add_node("recommend_product_agent", make_recommend_product_node(recommend_graph))
    workflow.add_node("generate_message_agent", make_generate_message_node(generate_message_graph))
    workflow.add_node("data_registration_agent", make_data_registration_node(data_registration_graph))

    workflow.add_edge(START, "supervisor")
    workflow.add_edge("supervisor", END)

    return workflow.compile(checkpointer=checkpointer)
