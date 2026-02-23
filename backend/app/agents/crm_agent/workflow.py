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


def should_retry_after_quality_check(state: CRMState) -> str:
    """
    품질 검사 결과에 따라 다음 노드를 결정하는 조건부 엣지

    - 통과(completed) → END
    - 실패 + retry_count < 2 → create_product_message (피드백 반영 재생성)
    - 실패 + retry_count >= 2 → END (최대 재시도 초과, failed)
    """
    if state.get("status") == "completed":
        return "__end__"

    retry_count = state.get("intermediate", {}).get("quality_check", {}).get("retry_count", 0)
    if retry_count < 2:
        return "create_product_message"
    return "__end__"


def should_continue_after_recommendation(state: CRMState) -> str:
    """
    상품 추천 결과에 따라 다음 노드를 결정하는 조건부 엣지

    - 실패(failed) → END (에러 상태로 종료)
    - 정상 → create_product_message
    """
    if state.get("status") == "failed":
        return "__end__"
    return "create_product_message"


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
    2. recommend_products_node: 상품 추천 (상위 3개)
       → interrupt()로 일시 중단, 사용자 상품 선택 대기
       → Command(resume=product_id)로 재개
    3. create_product_message_node: 선택된 상품에 대한 메시지 생성
    4. quality_check_node: 생성된 메시지 품질 검사 (3단계)
    5. END: 종료

    Args:
        checkpointer: LangGraph checkpointer (기본값: MemorySaver)
                      interrupt/resume을 위해 반드시 필요

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

    # 사용자 선택 대기는 recommend_products_node 내부의 interrupt()가 처리
    # 에러 발생 시 create_product_message로 넘어가지 않도록 조건부 엣지 사용
    workflow.add_conditional_edges(
        "recommend_products",
        should_continue_after_recommendation,
        {
            "create_product_message": "create_product_message",
            "__end__": END,
        }
    )

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
    print("  2. recommend_products - 상품 추천")
    print("  3. create_product_message - 메시지 생성")
    print("  4. quality_check - 메시지 품질 검사")

    print("\n[워크플로우]")
    print("  parse_crm_request → recommend_products → create_product_message → quality_check → END")

    print("\n=" * 80)
    print("워크플로우 구성 완료")
    print("=" * 80)
