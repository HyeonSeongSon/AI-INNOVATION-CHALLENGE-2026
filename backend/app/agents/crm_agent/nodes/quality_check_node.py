"""
품질 검사 노드

생성된 마케팅 메시지의 품질을 3단계로 검증하는 노드
1. Rule-based Check (비용 0)
2. LLM-as-a-Judge (LLM 1회 호출)
3. Groundedness Check (비용 0)
"""

import os
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from ..state import CRMState
from ....core.llm_factory import create_llm
from ..services.quality_check import QualityChecker
from ....core.logging import AgentLogger


# QualityChecker 인스턴스 
_checker = QualityChecker()


async def quality_check_node(state: CRMState, config: RunnableConfig) -> Dict[str, Any]:
    """
    생성된 메시지의 품질을 검증하는 노드

    3단계 검사를 순차 실행하며, 실패 시 단락(short-circuit)합니다.

    Args:
        state: CRMState - 현재 상태

    Returns:
        Dict[str, Any]: 업데이트할 상태

    State READ:
        - intermediate.message.messages
        - intermediate.message.selected_product
        - intermediate.message.product_document_summary
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
        selected_product = message_context.get("selected_product", {})
        product_document_summary = message_context.get("product_document_summary")
        persona_info = intermediate.get("recommendation", {}).get("persona_info", {})
        purpose = intermediate.get("request", {}).get("parsed_request", {}).get("purpose", "브랜드/제품 소개")

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

        # 2. config에서 모델명 읽기 후 LLM 생성
        model_name = config.get("configurable", {}).get("model", os.getenv("CHATGPT_MODEL_NAME"))
        llm = create_llm(model_name, temperature=0)

        # 3. 각 메시지에 대해 품질 검사 실행
        results = []
        all_passed = True

        product_id = selected_product.get("product_id")

        for msg in messages:
            brand_name = msg.get("brand", "")
            product_name = msg.get("product_name", "")

            logger.info(
                "checking_message",
                user_message=f"메시지 품질 검사 중: {product_name}",
                product_id=product_id,
            )

            with logger.track_duration(
                "quality_check",
                user_message=f"품질 검사 진행 중: {product_name}",
            ):
                result = await _checker.check_quality(
                    message=msg,
                    product=selected_product,
                    persona_info=persona_info,
                    purpose=purpose,
                    brand_name=brand_name,
                    product_document_summary=product_document_summary,
                    llm=llm,
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
            failed_result = next((r for r in results if not r.get("passed")), {})

            # 피드백 조합: failure_reason + LLM 피드백
            failure_reason = failed_result.get("failure_reason", "")
            llm_feedback = (failed_result.get("llm_judge_scores") or {}).get("feedback", "")
            feedback = failure_reason
            if llm_feedback:
                feedback = f"{failure_reason}\nLLM 피드백: {llm_feedback}"

            # 재시도 카운터 읽기 및 증가
            retry_count = intermediate.get("quality_check", {}).get("retry_count", 0)
            intermediate["quality_check"]["feedback"] = feedback
            intermediate["quality_check"]["retry_count"] = retry_count + 1

            # 실패한 메시지 원문 저장 (재생성 시 컨텍스트로 활용)
            failed_index = next((i for i, r in enumerate(results) if not r.get("passed")), None)
            if failed_index is not None and failed_index < len(messages):
                intermediate["quality_check"]["previous_message"] = messages[failed_index].get("full_content", "")

            # 최대 재시도(2회) 초과 여부에 따라 status 구분
            if retry_count >= 2:
                final_status = "failed"
                log_message = f"품질 검사 최대 재시도 초과 ({retry_count + 1}/3회): {failed_count}/{len(results)}건 미통과"
            else:
                final_status = "quality_check_failed"
                log_message = f"품질 검사 미통과 ({retry_count + 1}/3회): {failed_count}/{len(results)}건 미통과 — 재생성 예정"

            logger.warning(
                "node_completed_with_failures",
                user_message=log_message,
                total_messages=len(results),
                failed_count=failed_count,
                retry_count=retry_count + 1,
            )
            return {
                "step": state.get("step", 0) + 1,
                "last_node": "quality_check_node",
                "current_node": "end",
                "intermediate": intermediate,
                "logs": logger.get_user_logs(),
                "status": final_status,
                "error": f"품질 검사 미통과: {failure_reason}",
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
