from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from ..base.base_state import BaseState


class SupervisorState(BaseState, total=False):
    """
    Supervisor Agent용 State (대화형 챗봇)

    입력: messages (HumanMessage append 방식)
    - add_messages reducer로 invoke할 때마다 대화 이력이 누적됨
    - LangGraph checkpointer와 함께 thread_id 기반 세션 유지

    subgraph 공유 필드:
    - input: CRM subgraph에 전달할 원본 텍스트 (supervisor_node에서 설정)
    - step, logs, intermediate, status: BaseState 상속 (CRMState와 key 공유)
    """
    messages: Annotated[list[AnyMessage], add_messages]
    input: str  # CRM subgraph 진입 시 supervisor_node가 설정
