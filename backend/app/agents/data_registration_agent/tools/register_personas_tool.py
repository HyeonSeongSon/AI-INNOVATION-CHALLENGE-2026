import asyncio
import json
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

logger = get_logger("register_personas_tool")
_semaphore = asyncio.Semaphore(5)


async def _process_one(index: int, record: dict, llm, persona_client, user_id: str | None = None) -> dict:
    try:
        messages = [HumanMessage(content=json.dumps(record, ensure_ascii=False, indent=2))]
        structured_persona, raw_queries = await asyncio.gather(
            generate_structured_persona_info(messages, llm),
            generate_search_query(messages, llm),
        )
        persona_id = await persona_client.save_persona(structured_persona, user_id=user_id)
        await persona_client.save_product_search_query(persona_id, raw_queries)
        return {
            "index": index,
            "success": True,
            "persona_id": persona_id,
            "persona_name": structured_persona.get("name"),
        }
    except Exception as e:
        logger.error("persona_record_failed", index=index, error_type=type(e).__name__)
        return {"index": index, "success": False, "error": "페르소나 생성 중 오류가 발생했습니다."}


@tool
async def register_personas_tool(
    state: Annotated[DataRegistrationState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """페르소나 파일을 일괄 등록합니다. 페르소나 레코드(이름, 나이, 피부타입 등)가 포함된 파일일 때 호출하세요."""
    persona_client = config["configurable"]["services"].persona_client
    user_id = config.get("configurable", {}).get("user_id")
    records = state.get("file_records") or []
    llm = get_llm(settings.chatgpt_model_name, temperature=0.3)

    async def _bounded(i: int, rec: dict):
        async with _semaphore:
            return await _process_one(i, rec, llm, persona_client, user_id=user_id)

    results = await asyncio.gather(*[_bounded(i, r) for i, r in enumerate(records)])

    succeeded = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    summary = f"**{len(succeeded)}명 페르소나 등록 완료**"
    if failed:
        lines = "\n".join(f"- {r['index'] + 1}번째: {r['error']}" for r in failed)
        summary += f" ({len(failed)}명 실패)\n\n**실패 목록:**\n{lines}"
    if succeeded:
        lines = "\n".join(
            f"- {r.get('persona_name') or '(이름 없음)'} `{r['persona_id']}`"
            for r in succeeded
        )
        summary += f"\n\n**생성된 페르소나:**\n{lines}"

    logger.info(
        "register_personas_tool_done",
        total=len(results),
        succeeded=len(succeeded),
        failed=len(failed),
    )

    return Command(
        update={
            "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            "file_records": None,
            "status": "completed",
            "logs": [f"페르소나 등록: {len(succeeded)}명 성공, {len(failed)}명 실패"],
        },
    )
