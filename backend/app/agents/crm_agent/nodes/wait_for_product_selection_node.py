"""
사용자 상품 선택 대기 노드 (HITL interrupt)

recommend_products_node에서 추천 결과를 state에 저장한 뒤,
이 노드에서 interrupt()를 호출하여 사용자 선택을 기다립니다.

분리한 이유:
    interrupt()는 내부적으로 GraphInterrupt를 raise하므로
    같은 노드에서 추천 로직과 interrupt()를 함께 두면
    return 문이 실행되지 않아 추천 결과가 체크포인트에 저장되지 않는 버그가 발생합니다.
    노드를 분리하면 recommend_products_node의 return이 정상 실행된 후
    체크포인트에 저장된 상태에서 이 노드가 interrupt()를 호출합니다.
"""

from typing import Dict, Any
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from ..state import CRMState
from ....core.logging import AgentLogger


async def wait_for_product_selection_node(state: CRMState) -> Dict[str, Any]:
    """
    추천된 상품 목록을 사용자에게 제시하고 선택을 기다리는 노드

    interrupt() 반환값(= Command(resume=selected_product_id))을
    intermediate.hitl.product_selection에 저장합니다.
    """
    logger = AgentLogger(state, node_name="wait_for_product_selection_node")
    intermediate = state.get("intermediate", {})

    if "hitl" not in intermediate:
        intermediate["hitl"] = {}

    hitl = intermediate["hitl"]
    recommendation = intermediate.get("recommendation", {})
    recommended_products = recommendation.get("recommended_products", [])
    persona_info = recommendation.get("persona_info")

    logger.info(
        "waiting_for_product_selection",
        user_message="추천 상품을 사용자에게 제시합니다. 상품을 선택해주세요.",
        product_count=len(recommended_products),
    )

    try:
        # 서브그래프 interrupt 규칙:
        # 이 노드는 부모 graph(SupervisorState) 안의 서브그래프 내부에서 실행됨.
        # interrupt() 발생 시 서브그래프가 return하지 않으므로 부모 state의
        # intermediate가 갱신되지 않음.
        # → 부모에서 필요한 모든 데이터는 interrupt(value)에 명시적으로 포함해야 함.
        hitl["product_selection"] = interrupt({
            "type": "product_selection",
            "recommended_products": recommended_products,
            "persona_info": persona_info,
            # 향후 부모에서 필요한 데이터 추가 시 여기에 포함할 것
        })


        selected_product_id = hitl["product_selection"]
        logger.info(
            "product_selected_by_user",
            user_message=f"사용자 선택 완료: {selected_product_id}",
            selected_product_id=selected_product_id,
        )

        return {
            "step": state.get("step", 0) + 1,
            "last_node": "wait_for_product_selection_node",
            "current_node": "create_product_message",
            "intermediate": intermediate,
            "logs": logger.get_user_logs(),
            "status": "running",
        }

    except GraphInterrupt:
        raise
