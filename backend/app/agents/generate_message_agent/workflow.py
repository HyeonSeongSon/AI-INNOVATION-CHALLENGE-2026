from langgraph.graph import StateGraph, START, END
from .nodes import init_node, router_node, quality_check_node, generate_message_node, message_feedback_node, output_node, _MAX_RETRIES
from .state import GenerateMessageState

def _route_after_router(state: GenerateMessageState) -> str:
    return state["decisions"]["next_node"]


def _route_after_quality_check(state: GenerateMessageState) -> str:
    failed_task_ids = set(state.get("failed_task_ids") or [])
    if not failed_task_ids:
        return "output_node"

    generated_tasks = state.get("generated_tasks") or []
    unrecoverable = any(
        t.get("quality_check", {}).get("failed_stage") == "product_fetch"
        or any(
            r.get("error") == "api_unavailable"
            for r in t.get("quality_check", {}).get("semantic_check_results", [])
        )
        for t in generated_tasks
        if t["product_id"] in failed_task_ids
    )
    if unrecoverable:
        return "output_node"

    if state.get("feedback_retry_count", 0) >= _MAX_RETRIES:
        return "output_node"

    return "message_feedback_node"


def _route_after_feedback(state: GenerateMessageState) -> str:
    """피드백 적용 후 항상 품질 검사 실행 — max retries 종결은 _route_after_quality_check에서 처리."""
    return "quality_check_node"


def build_workflow(checkpointer=None):
    workflow = StateGraph(GenerateMessageState)

    workflow.add_node("init_node", init_node)
    workflow.add_node("router_node", router_node)
    workflow.add_node("generate_message_node", generate_message_node)
    workflow.add_node("quality_check_node", quality_check_node)
    workflow.add_node("message_feedback_node", message_feedback_node)
    workflow.add_node("output_node", output_node)

    workflow.add_edge(START, "init_node")
    workflow.add_edge("init_node", "router_node")
    workflow.add_conditional_edges(
        "router_node",
        _route_after_router,
        {
            "generate_message_node": "generate_message_node",
            "message_feedback_node": "message_feedback_node",
            "output_node": "output_node",
        },
    )
    workflow.add_edge("generate_message_node", "quality_check_node")
    workflow.add_conditional_edges(
        "quality_check_node",
        _route_after_quality_check,
        {"message_feedback_node": "message_feedback_node", "output_node": "output_node"},
    )
    # static edge 대신 conditional edge — Command와 static edge 충돌로 인한 무한루프 방지
    workflow.add_conditional_edges(
        "message_feedback_node",
        _route_after_feedback,
        {"quality_check_node": "quality_check_node", "output_node": "output_node"},
    )
    workflow.add_edge("output_node", END)

    return workflow.compile(checkpointer=checkpointer)

