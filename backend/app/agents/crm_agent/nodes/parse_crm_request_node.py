"""
CRM 요청 파싱 노드

사용자 입력을 구조화된 CRM 요청으로 파싱하는 노드
"""

import os
import json
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from ..state import CRMState
from ..services.parse_crm_request import MultiValueParser
from ....core.logging import AgentLogger
from ....core.llm_factory import get_llm


# Parser 인스턴스 
_parser = MultiValueParser()


async def parse_crm_request_node(state: CRMState, config: RunnableConfig) -> Dict[str, Any]:
    """
    사용자 입력을 파싱하여 구조화된 CRM 요청으로 변환하는 노드

    Args:
        state: CRMState - 현재 상태

    Returns:
        Dict[str, Any]: 업데이트할 상태

    State 업데이트:
        - intermediate.request.parsed_request: 파싱된 요청 데이터
        - logs: 파싱 로그 추가
        - step: step 증가
        - last_node: 현재 노드명 기록
        - current_node: 다음 노드로 업데이트
    """

    logger = AgentLogger(state, node_name="parse_crm_request_node")
    intermediate = state.get("intermediate", {})

    logger.info(
        "node_started",
        user_message="parse_crm_request_node 시작",
    )

    try:
        # 사용자 입력 가져오기
        user_input = state.get("input")

        if not user_input:
            raise ValueError("입력(input)이 비어있습니다.")

        logger.info(
            "input_received",
            user_message=f"사용자 입력: {user_input}",
            input_length=len(user_input),
        )

        # config에서 모델명 읽기 (없으면 환경변수 기본값)
        model_name = config.get("configurable", {}).get("model", os.getenv("CHATGPT_MODEL_NAME"))
        llm = get_llm(model_name, temperature=0)

        # 파싱 수행 (JSON 문자열 반환)
        with logger.track_duration("llm_parse", user_message="LLM 파싱 수행 중..."):
            parsed_json = await _parser.parse(user_input, llm=llm)

        # JSON 문자열을 딕셔너리로 변환
        parsed_data = json.loads(parsed_json)

        logger.info(
            "parse_completed",
            user_message=f"파싱 완료: {parsed_data}",
            persona_id=parsed_data.get("persona_id"),
            brands=parsed_data.get("brands"),
            categories=parsed_data.get("product_categories"),
        )

        # Context 구조로 저장
        if "request" not in intermediate:
            intermediate["request"] = {}
        intermediate["request"]["parsed_request"] = parsed_data

        # 상태 업데이트
        return {
            "step": state.get("step", 0) + 1,
            "last_node": "parse_crm_request_node",
            "current_node": "recommend_products_node",  # 다음 노드
            "intermediate": intermediate,
            "logs": logger.get_user_logs(),
            "status": "running"
        }

    except Exception as e:
        # 에러 처리
        error_msg = f"파싱 중 오류 발생: {str(e)}"
        logger.error(
            "node_failed",
            user_message=f"ERROR: {error_msg}",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )

        return {
            "step": state.get("step", 0) + 1,
            "last_node": "parse_crm_request_node",
            "current_node": "error_handler",  # 에러 핸들러로 이동
            "error": error_msg,
            "error_details": {
                "node": "parse_crm_request_node",
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            },
            "logs": logger.get_user_logs(),
            "status": "failed"
        }