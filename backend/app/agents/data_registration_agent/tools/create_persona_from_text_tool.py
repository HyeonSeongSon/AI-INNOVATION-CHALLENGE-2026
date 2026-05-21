from typing import Annotated

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ...shared.persona.generate_persona_and_query import (
    generate_structured_persona_info,
    generate_search_query,
)
from ....core.llm_factory import get_llm
from ....config.settings import settings
from ....core.logging import get_logger
from ..state import DataRegistrationState

logger = get_logger("create_persona_from_text_tool")


@tool
async def create_persona_from_text_tool(
    state: Annotated[DataRegistrationState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """자연어로 설명된 페르소나를 구조화하여 DB에 등록합니다.
    사용자가 페르소나 특성(나이, 성별, 직업, 피부타입, 고민 등)을 텍스트로 설명했을 때 호출하세요."""
    persona_client = config["configurable"]["services"].persona_client
    # HumanMessage만 추출 — AIMessage(tool_calls)가 섞이면 OpenAI API 400 에러 발생
    human_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    llm = get_llm(settings.chatgpt_model_name, temperature=0.3)

    try:
        structured_persona = await generate_structured_persona_info(human_messages, llm)
        persona_id = await persona_client.save_persona(structured_persona)
        raw_queries = await generate_search_query(human_messages, llm)
        await persona_client.save_product_search_query(persona_id, raw_queries)

        summary = (
            f"**페르소나 등록 완료**\n\n"
            f"- 이름: {structured_persona.get('name') or '(이름 없음)'}\n"
            f"- ID: `{persona_id}`"
        )
        logger.info("create_persona_from_text_done", persona_id=persona_id, name=structured_persona.get("name"))
    except Exception as e:
        logger.error("create_persona_from_text_failed", error=str(e))
        summary = f"**페르소나 등록 실패**\n\n{e}"

    return Command(
        update={
            "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            "status": "completed",
            "logs": [summary.splitlines()[0]],
        },
    )
