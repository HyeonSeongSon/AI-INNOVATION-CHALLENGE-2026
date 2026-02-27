from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict


class BaseState(TypedDict, total=False):
    """
    모든 Agent State의 베이스

    설계 원칙:
    - interrupt / resume 가능해야 함
    - graph 재진입 안전
    - node 간 공유 데이터 명확
    - 상태 추적 및 디버깅 용이

    NOTE: input / messages 는 에이전트마다 형태가 다르므로 각 State에서 정의
    - 단발성 에이전트: input: str (원본 텍스트)
    - 대화형 에이전트: messages: Annotated[list[AnyMessage], add_messages]
    """

    # -------------------------
    # 기본 정보
    # -------------------------
    context: Dict[str, Any]         # 실행 컨텍스트 (session, user, meta)

    # -------------------------
    # 실행 상태 관리
    # -------------------------
    step: int                       # 현재 step (기본값: 0)
    max_steps: int                  # 최대 허용 step (무한루프 방지)
    last_node: str                  # 마지막 실행 node
    current_node: str               # 현재 실행 중인 node
    node_history: List[str]         # node 실행 이력 (디버깅용)
    is_interrupted: bool            # interrupt 여부
    status: Literal["running", "completed", "failed", "interrupted"]  # 실행 상태

    # -------------------------
    # 에이전트 판단 / 중간 결과
    # -------------------------
    decisions: Dict[str, Any]       # 분기 판단 결과
    intermediate: Dict[str, Any]    # node 중간 산출물

    # -------------------------
    # Tool / 외부 호출 결과
    # -------------------------
    tool_results: Dict[str, Any]    # tool 실행 결과
    tool_calls: List[Dict[str, Any]]  # tool 호출 이력

    # -------------------------
    # 최종 결과
    # -------------------------
    output: Any                     # 최종 출력 결과

    # -------------------------
    # 에러 / 로그
    # -------------------------
    error: Optional[str]            # 에러 메시지
    error_details: Optional[Dict[str, Any]]  # 상세 에러 정보 (traceback 등)
    logs: List[str]                 # 실행 로그

    # -------------------------
    # 타이밍 / 성능
    # -------------------------
    start_time: Optional[str]       # 실행 시작 시간 (ISO format)
    end_time: Optional[str]         # 실행 종료 시간 (ISO format)
    duration_ms: Optional[float]    # 실행 소요 시간 (밀리초)

    # -------------------------
    # 메타데이터
    # -------------------------
    metadata: Dict[str, Any]        # 추가 메타데이터 (확장 가능)