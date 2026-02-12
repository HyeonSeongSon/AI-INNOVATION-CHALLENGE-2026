"""
품질 검사 노드

생성된 마케팅 메시지의 품질을 3단계로 검증하는 노드
1. Rule-based Check (비용 0)
2. LLM-as-a-Judge (LLM 1회 호출)
3. Groundedness Check (비용 0)
"""

from typing import Dict, Any
from ..state import CRMState
from ..services.quality_check import QualityChecker
from ....core.logging import AgentLogger


# QualityChecker 싱글톤 인스턴스 (재사용)
_checker_instance = None


def get_quality_checker() -> QualityChecker:
    """QualityChecker 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = QualityChecker()
    return _checker_instance


async def quality_check_node(state: CRMState) -> Dict[str, Any]:
    """
    생성된 메시지의 품질을 검증하는 노드

    3단계 검사를 순차 실행하며, 실패 시 단락(short-circuit)합니다.

    Args:
        state: CRMState - 현재 상태

    Returns:
        Dict[str, Any]: 업데이트할 상태

    State READ:
        - intermediate.message.messages
        - intermediate.recommendation.recommended_products
        - intermediate.recommendation.persona_info
        - intermediate.request.parsed_request

    State WRITE:
        - intermediate.quality_check.results
    """

    logger = AgentLogger(state, node_name="quality_check_node")
    intermediate = state.get("intermediate", {})

    logger.info(
        "node_started",
        user_message="quality_check_node 시작",
    )

    try:
        # 1. 필요한 데이터 추출
        message_context = intermediate.get("message", {})
        messages = message_context.get("messages", [])
        recommendation = intermediate.get("recommendation", {})
        recommended_products = recommendation.get("recommended_products", [])
        persona_info = recommendation.get("persona_info", {})
        request_context = intermediate.get("request", {})
        parsed_request = request_context.get("parsed_request", {})
        purpose = parsed_request.get("purpose", "브랜드/제품 소개")

        # Context 구조 초기화
        if "quality_check" not in intermediate:
            intermediate["quality_check"] = {}

        if not messages:
            logger.warning(
                "no_messages",
                user_message="검사할 메시지가 없습니다.",
            )
            intermediate["quality_check"]["results"] = []

            return {
                "step": state.get("step", 0) + 1,
                "last_node": "quality_check_node",
                "current_node": "end",
                "intermediate": intermediate,
                "logs": logger.get_user_logs(),
                "status": "completed",
            }

        # 2. QualityChecker 가져오기
        checker = get_quality_checker()

        # 3. 각 메시지에 대해 품질 검사 실행
        results = []
        all_passed = True

        for msg in messages:
            product_id = msg.get("product_id")
            brand_name = msg.get("brand", "")
            product_name = msg.get("product_name", "")

            # 매칭되는 상품 데이터 찾기
            product = next(
                (p for p in recommended_products if p.get("product_id") == product_id),
                {},
            )

            logger.info(
                "checking_message",
                user_message=f"메시지 품질 검사 중: {product_name}",
                product_id=product_id,
            )

            with logger.track_duration(
                "quality_check",
                user_message=f"품질 검사 진행 중: {product_name}",
            ):
                result = await checker.check_quality(
                    message=msg,
                    product=product,
                    persona_info=persona_info,
                    purpose=purpose,
                    brand_name=brand_name,
                )

            results.append(result)

            if result.get("passed"):
                scores = result.get("llm_judge_scores", {})
                overall = scores.get("overall", 0) if scores else 0
                logger.info(
                    "message_passed",
                    user_message=f"품질 검사 통과: {product_name} (종합 {overall}점)",
                    product_id=product_id,
                )
            else:
                all_passed = False
                failed_stage = result.get("failed_stage", "unknown")
                failure_reason = result.get("failure_reason", "알 수 없는 오류")
                logger.warning(
                    "message_failed",
                    user_message=f"품질 검사 실패 ({failed_stage}): {failure_reason}",
                    product_id=product_id,
                    failed_stage=failed_stage,
                )

        # 4. 결과 저장
        intermediate["quality_check"]["results"] = results

        # 5. 최종 상태 결정
        if all_passed:
            logger.info(
                "node_completed",
                user_message=f"품질 검사 완료: 모든 메시지 통과 ({len(results)}건)",
                total_messages=len(results),
            )
            return {
                "step": state.get("step", 0) + 1,
                "last_node": "quality_check_node",
                "current_node": "end",
                "intermediate": intermediate,
                "logs": logger.get_user_logs(),
                "status": "completed",
            }
        else:
            failed_count = sum(1 for r in results if not r.get("passed"))
            logger.warning(
                "node_completed_with_failures",
                user_message=f"품질 검사 완료: {failed_count}/{len(results)}건 미통과",
                total_messages=len(results),
                failed_count=failed_count,
            )
            return {
                "step": state.get("step", 0) + 1,
                "last_node": "quality_check_node",
                "current_node": "end",
                "intermediate": intermediate,
                "logs": logger.get_user_logs(),
                "status": "failed",
                "error": f"품질 검사 미통과: {results[0].get('failure_reason', '')}",
                "error_details": {
                    "node": "quality_check_node",
                    "failed_results": [r for r in results if not r.get("passed")],
                },
            }

    except Exception as e:
        error_msg = f"품질 검사 중 오류 발생: {str(e)}"
        logger.error(
            "node_failed",
            user_message=f"ERROR: {error_msg}",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )

        return {
            "step": state.get("step", 0) + 1,
            "last_node": "quality_check_node",
            "current_node": "error_handler",
            "error": error_msg,
            "error_details": {
                "node": "quality_check_node",
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            },
            "logs": logger.get_user_logs(),
            "status": "failed",
        }
