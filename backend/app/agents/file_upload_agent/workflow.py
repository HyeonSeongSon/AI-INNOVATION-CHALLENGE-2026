from langgraph.graph import StateGraph, START

from .state import FileUploadState
from .nodes import init_node, file_upload_agent_node


def build_workflow(checkpointer=None):
    workflow = StateGraph(FileUploadState)

    workflow.add_node("init_node", init_node)
    workflow.add_node("file_upload_agent", file_upload_agent_node)

    workflow.add_edge(START, "init_node")
    workflow.add_edge("init_node", "file_upload_agent")
    # 툴의 Command(goto=END)가 그래프를 종료하므로 명시적 엣지 불필요

    return workflow.compile(checkpointer=checkpointer)


# LangGraph Studio용
graph = build_workflow()
