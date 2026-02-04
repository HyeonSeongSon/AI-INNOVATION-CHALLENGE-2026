"""
CRM 요청 파싱 노드

사용자 입력을 구조화된 CRM 요청으로 파싱하는 노드
"""

import json
from typing import Dict, Any
from ..state import CRMState
from ..services.parse_crm_request import MultiValueParser


# Parser 싱글톤 인스턴스 (재사용)
_parser_instance = None


def get_parser() -> MultiValueParser:
    """Parser 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = MultiValueParser()
    return _parser_instance


def parse_crm_request_node(state: CRMState) -> Dict[str, Any]:
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

    # 현재 step과 로그 초기화
    current_step = state.get("step", 0)
    logs = state.get("logs", [])
    intermediate = state.get("intermediate", {})

    # 로그 추가
    logs.append(f"[Step {current_step}] parse_crm_request_node 시작")

    try:
        # 사용자 입력 가져오기
        user_input = state.get("input")

        if not user_input:
            raise ValueError("입력(input)이 비어있습니다.")

        logs.append(f"[Step {current_step}] 사용자 입력: {user_input}")

        # Parser 가져오기
        parser = get_parser()

        # 파싱 수행 (JSON 문자열 반환)
        parsed_json = parser.parse(user_input)

        # JSON 문자열을 딕셔너리로 변환
        parsed_data = json.loads(parsed_json)

        logs.append(f"[Step {current_step}] 파싱 완료: {parsed_data}")

        # Context 구조로 저장
        if "request" not in intermediate:
            intermediate["request"] = {}
        intermediate["request"]["parsed_request"] = parsed_data

        # 상태 업데이트
        return {
            "step": current_step + 1,
            "last_node": "parse_crm_request_node",
            "current_node": "recommend_products_node",  # 다음 노드
            "intermediate": intermediate,
            "logs": logs,
            "status": "running"
        }

    except Exception as e:
        # 에러 처리
        error_msg = f"파싱 중 오류 발생: {str(e)}"
        logs.append(f"[Step {current_step}] ERROR: {error_msg}")

        return {
            "step": current_step + 1,
            "last_node": "parse_crm_request_node",
            "current_node": "error_handler",  # 에러 핸들러로 이동
            "error": error_msg,
            "error_details": {
                "node": "parse_crm_request_node",
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            },
            "logs": logs,
            "status": "failed"
        }


if __name__ == "__main__":
    """
    노드 테스트
    """
    from pprint import pprint

    # 테스트 state 생성
    test_state: CRMState = {
        "input": "PERSONA_002로 설화수 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘",
        "step": 0,
        "logs": [],
        "intermediate": {},
        "context": {
            "user_id": "test_user",
            "session_id": "test_session"
        }
    }

    print("=" * 60)
    print("테스트 입력:")
    print(f"  {test_state['input']}")
    print("=" * 60)

    # 노드 실행
    result = parse_crm_request_node(test_state)

    print("\n" + "=" * 60)
    print("실행 결과:")
    print("=" * 60)
    pprint(result, width=80, indent=2)

    print("\n" + "=" * 60)
    print("파싱된 데이터:")
    print("=" * 60)
    if "intermediate" in result and "request" in result["intermediate"]:
        pprint(result["intermediate"]["request"]["parsed_request"], width=80, indent=2)
    else:
        print("파싱 실패")
