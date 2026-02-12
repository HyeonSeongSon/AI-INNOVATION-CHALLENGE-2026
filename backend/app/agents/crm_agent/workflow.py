"""
CRM Agent Workflow

LangGraph를 사용한 CRM Agent 워크플로우 정의
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import CRMState
from .nodes.parse_crm_request_node import parse_crm_request_node
from .nodes.recommend_products_node import recommend_products_node
from .nodes.create_product_message_node import create_product_message_node
from .nodes.quality_check_node import quality_check_node


def should_continue_to_message(state: CRMState) -> str:
    """
    사용자 선택 여부에 따라 다음 노드를 결정하는 조건부 엣지

    Args:
        state: CRMState

    Returns:
        str: 다음 노드 이름 ("create_product_message" 또는 "__end__")
    """
    # 사용자가 상품을 선택했는지 확인
    selected_product_id = state.get("selected_product_id")

    if selected_product_id is not None:
        # 선택된 상품이 있으면 메시지 생성으로 이동
        return "create_product_message"
    else:
        # 선택된 상품이 없으면 사용자 입력 대기 (interrupt)
        return "human_input_required"


def build_crm_workflow(checkpointer=None):
    """
    CRM Agent 워크플로우 구성

    워크플로우:
    1. parse_crm_request_node: 사용자 입력 파싱
    2. recommend_products_node: 상품 추천 (상위 3개)
    3. INTERRUPT: 사용자에게 상품 선택 요청 (Human-in-the-loop)
    4. create_product_message_node: 선택된 상품에 대한 메시지 생성
    5. quality_check_node: 생성된 메시지 품질 검사 (3단계)
    6. END: 종료

    Args:
        checkpointer: LangGraph checkpointer (기본값: MemorySaver)
                      사용자 입력 대기 및 재개를 위해 필요

    Returns:
        CompiledGraph: 컴파일된 LangGraph (interrupt 지원)
    """
    # Checkpointer 설정 (기본값: MemorySaver)
    if checkpointer is None:
        checkpointer = MemorySaver()

    # StateGraph 생성
    workflow = StateGraph(CRMState)

    # 노드 추가
    workflow.add_node("parse_crm_request", parse_crm_request_node)
    workflow.add_node("recommend_products", recommend_products_node)
    workflow.add_node("create_product_message", create_product_message_node)
    workflow.add_node("quality_check", quality_check_node)

    # 시작점 설정
    workflow.set_entry_point("parse_crm_request")

    # 엣지 추가
    workflow.add_edge("parse_crm_request", "recommend_products")

    # recommend_products 후 조건부 엣지
    # - selected_product_id가 있으면 create_product_message로 이동
    # - 없으면 interrupt (사용자 입력 대기)
    workflow.add_conditional_edges(
        "recommend_products",
        should_continue_to_message,
        {
            "create_product_message": "create_product_message",
            "human_input_required": END  # interrupt 후 대기
        }
    )
    workflow.add_edge("create_product_message", "quality_check")
    workflow.add_edge("quality_check", END)
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
    print("  2. recommend_products - 상품 추천")
    print("  3. create_product_message - 메시지 생성")
    print("  4. quality_check - 메시지 품질 검사")

    print("\n[워크플로우]")
    print("  parse_crm_request → recommend_products → create_product_message → quality_check → END")

    print("\n=" * 80)
    print("워크플로우 구성 완료")
    print("=" * 80)
