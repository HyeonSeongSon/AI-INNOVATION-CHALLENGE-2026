import uuid
from typing import Annotated

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.tools import InjectedToolCallId
from langgraph.types import Command


@tool
def handoff_to_recommend_product_agent(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """상품 추천 에이전트로 제어를 이전합니다. 사용자가 상품 추천을 요청할 때 호출하세요."""
    return Command(
        goto="recommend_product_agent",
        update={
            "messages": [
                ToolMessage(
                    content="상품 추천 에이전트로 핸드오프합니다.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )


@tool
def handoff_to_generate_message_agent(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """메시지 생성 에이전트로 제어를 이전합니다. 사용자가 CRM 메시지 생성을 요청할 때 호출하세요."""
    return Command(
        goto="generate_message_agent",
        update={
            "messages": [
                ToolMessage(
                    content="메시지 생성 에이전트로 핸드오프합니다.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )

@tool
def handoff_to_search_agent(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """검색 에이전트로 제어를 이전합니다.
    페르소나 목록 조회·검색, 특정 페르소나 상세 조회, 브랜드·카테고리·메시지 타입 목록 확인,
    브랜드나 상품 종류별 인기 상품 조회 등 데이터 조회·검색을 요청할 때 호출하세요."""
    return Command(
        goto="search_agent",
        update={
            "messages": [
                ToolMessage(
                    content="검색 에이전트로 핸드오프합니다.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )


@tool
def handoff_to_data_registration_agent(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """데이터 등록 에이전트로 제어를 이전합니다.
    파일로 일괄 등록하거나, 자연어로 페르소나를 설명하여 등록을 요청할 때 호출하세요."""
    return Command(
        goto="data_registration_agent",
        update={
            "messages": [
                ToolMessage(
                    content="데이터 등록 에이전트로 핸드오프합니다.",
                    tool_call_id=tool_call_id,
                )
            ]
        },
    )


def create_handoff_messages(
    agent_name: str,
) -> tuple[AIMessage, ToolMessage]:
    """에이전트에서 supervisor로 돌아갈 때 사용할 handoff back 메시지 쌍을 생성합니다."""
    tool_call_id = str(uuid.uuid4())
    tool_name = "transfer_back_to_supervisor"

    ai_message = AIMessage(
        content="Supervisor로 이동합니다.",
        name=agent_name,
        tool_calls=[{
            "name": tool_name,
            "args": {},
            "id": tool_call_id,
        }],
    )

    tool_message = ToolMessage(
        content="supervisor로 성공적으로 작업을 전달했습니다.",
        name=tool_name,
        tool_call_id=tool_call_id,
    )

    return ai_message, tool_message
