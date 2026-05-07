from langgraph.graph import StateGraph, START, END
from .state import RecommendProductState
from .nodes import init_node, parser_node, get_search_query_node, recommend_products_node

def route_after_search_query(state: RecommendProductState) -> str:
    if state.get("status") in ("failed", "completed"):
        return END
    if not state.get("search_queries"):
        return END
    return "recommend_products_node"

def build_workflow(checkpointer=None):
    workflow = StateGraph(RecommendProductState)

    workflow.add_node("init_node", init_node)
    workflow.add_node("parser_node", parser_node)
    workflow.add_node("get_search_query_node", get_search_query_node)
    workflow.add_node("recommend_products_node", recommend_products_node)

    workflow.add_edge(START, "init_node")
    workflow.add_edge("init_node", "parser_node")
    workflow.add_edge("parser_node", "get_search_query_node")
    workflow.add_conditional_edges(
        "get_search_query_node",
        route_after_search_query,
        {END: END, "recommend_products_node": "recommend_products_node"},
    )
    workflow.add_edge("recommend_products_node", END)

    return workflow.compile(checkpointer=checkpointer)

# LangGraph Studio용 모듈 레벨 graph 노출
graph = build_workflow()
