"""
CRM Agent Workflow

LangGraph를 사용한 CRM Agent 워크플로우 정의
"""

from langgraph.graph import StateGraph, END
from .state import CRMState
from .nodes.parse_crm_request_node import parse_crm_request_node
from .nodes.recommend_products_node import recommend_products_node
from .nodes.wait_for_product_selection_node import wait_for_product_selection_node
from .nodes.create_product_message_node import create_product_message_node
from .nodes.quality_check_node import quality_check_node


def should_retry_after_quality_check(state: CRMState) -> str:
    """
    품질 검사 결과에 따라 다음 노드를 결정하는 조건부 엣지

    - 통과(completed) → END
    - 실패 + retry_count < 3 → create_product_message (피드백 반영 재생성, 최대 2회)
    - 실패 + retry_count >= 3 → END (최대 재시도 초과, failed)
    """
    status = state.get("status")
    if status in ("completed", "failed"):
        return "__end__"

    retry_count = state.get("intermediate", {}).get("quality_check", {}).get("retry_count", 0)
    if retry_count < 3:
        return "create_product_message"
    return "__end__"


def should_continue_after_recommendation(state: CRMState) -> str:
    """
    상품 추천 결과에 따라 다음 노드를 결정하는 조건부 엣지

    - 실패(failed) → END (에러 상태로 종료)
    - 정상 → wait_for_product_selection
    """
    if state.get("status") == "failed":
        return "__end__"
    return "wait_for_product_selection"


def should_continue_after_message(state: CRMState) -> str:
    """
    메시지 생성 결과에 따라 다음 노드를 결정하는 조건부 엣지

    Args:
        state: CRMState

    Returns:
        str: 다음 노드 이름 ("quality_check" 또는 "__end__")
    """
    if state.get("status") == "failed":
        return "__end__"
    return "quality_check"


def build_crm_workflow(checkpointer=None):
    """
    CRM Agent 워크플로우 구성

    워크플로우:
    1. parse_crm_request_node: 사용자 입력 파싱
    2. recommend_products_node: 상품 추천 (상위 3개) → 결과를 state에 저장 후 정상 return
    3. wait_for_product_selection_node: interrupt()로 일시 중단, 사용자 상품 선택 대기
       → Command(resume=product_id)로 재개
    4. create_product_message_node: 선택된 상품에 대한 메시지 생성
    5. quality_check_node: 생성된 메시지 품질 검사 (3단계)
    6. END: 종료

    Args:
        checkpointer: LangGraph checkpointer (기본값: MemorySaver)
                      interrupt/resume을 위해 반드시 필요

    Returns:
        CompiledGraph: 컴파일된 LangGraph (interrupt 지원)
    """
    # # Checkpointer 설정 (기본값: MemorySaver)
    # if checkpointer is None:
    #     checkpointer = MemorySaver()

    # StateGraph 생성
    workflow = StateGraph(CRMState)

    # 노드 추가
    workflow.add_node("parse_crm_request", parse_crm_request_node)
    workflow.add_node("recommend_products", recommend_products_node)
    workflow.add_node("wait_for_product_selection", wait_for_product_selection_node)
    workflow.add_node("create_product_message", create_product_message_node)
    workflow.add_node("quality_check", quality_check_node)

    # 시작점 설정
    workflow.set_entry_point("parse_crm_request")

    workflow.add_edge("parse_crm_request", "recommend_products")

    # 추천 완료 후 사용자 선택 대기 노드로 이동 (에러 시 종료)
    workflow.add_conditional_edges(
        "recommend_products",
        should_continue_after_recommendation,
        {
            "wait_for_product_selection": "wait_for_product_selection",
            "__end__": END,
        }
    )

    # 사용자 선택 완료 후 메시지 생성 노드로 이동
    workflow.add_edge("wait_for_product_selection", "create_product_message")

    workflow.add_conditional_edges(
        "create_product_message",
        should_continue_after_message,
        {
            "quality_check": "quality_check",
            "__end__": END,
        }
    )
    
    workflow.add_conditional_edges(
        "quality_check",
        should_retry_after_quality_check,
        {
            "create_product_message": "create_product_message",
            "__end__": END,
        }
    )
    return workflow.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    """워크플로우 테스트"""
    print("=" * 80)
    print("CRM Agent Workflow 구성")
    print("=" * 80)

    # 워크플로우 빌드
    app = build_crm_workflow()

    print("\n[노드]")
    print("  1. parse_crm_request - 사용자 입력 파싱")
    print("  2. recommend_products - 상품 추천 (결과 저장 후 return)")
    print("  3. wait_for_product_selection - interrupt() 호출, 사용자 선택 대기")
    print("  4. create_product_message - 메시지 생성")
    print("  5. quality_check - 메시지 품질 검사")

    print("\n[워크플로우]")
    print("  parse_crm_request → recommend_products → wait_for_product_selection → create_product_message → quality_check → END")

    print("\n=" * 80)
    print("워크플로우 구성 완료")
    print("=" * 80)
