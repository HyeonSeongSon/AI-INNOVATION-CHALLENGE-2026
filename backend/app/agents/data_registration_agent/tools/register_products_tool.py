import asyncio
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ....core.logging import AgentLogger
from ....config.settings import settings
from ..state import DataRegistrationState

_semaphore = asyncio.Semaphore(settings.upload_product_concurrency)


@tool
async def register_products_tool(
    state: Annotated[DataRegistrationState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """상품 파일을 일괄 등록합니다. 상품 레코드(브랜드, 상품명, 상품상세_이미지 등)가 포함된 파일일 때 호출하세요."""
    _service = config["configurable"]["services"].registration
    logger = AgentLogger(state, node_name="register_products_tool", agent_name="data_registration_agent")

    records = state.get("file_records") or []

    logger.info(
        "product_bulk_registration_start",
        user_message=f"상품 등록 시작 — 총 {len(records)}개",
        total=len(records),
    )

    async def _bounded(rec: dict) -> dict:
        async with _semaphore:
            return await _service.register_product(rec)

    results = await asyncio.gather(
        *[_bounded(r) for r in records],
        return_exceptions=True,
    )

    succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]
    failed = [r for r in results if not (isinstance(r, dict) and r.get("success"))]

    summary = f"**{len(succeeded)}개 상품 등록 완료**"
    if failed:
        summary += f"\n실패: {len(failed)}개"

    logger.info(
        "product_bulk_registration_complete",
        user_message=f"완료 — 성공 {len(succeeded)}개 / 실패 {len(failed)}개",
        succeeded=len(succeeded),
        failed=len(failed),
    )

    return Command(
        update={
            "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            "file_records": None,
            "status": "completed",
            "logs": logger.get_user_logs(),
        },
    )
