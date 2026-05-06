import asyncio

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.graph import END

from ..state import MarketingAssistantState
from ..services.product_registration import get_product_registration_service
from ....core.logging import AgentLogger

_service = get_product_registration_service()


async def product_registration_node(state: MarketingAssistantState, config: RunnableConfig):
    """
    file_records에 담긴 JSONL 레코드를 병렬 처리해 상품을 일괄 등록한다.

    각 레코드는 register_product()를 통해:
    구조화 → 멀티벡터 생성 → OpenSearch 색인 → PostgreSQL 저장
    """
    logger = AgentLogger(state, node_name="product_registration_node")

    records = state.get("file_records") or []
    semaphore = asyncio.Semaphore(3)  # 동시 3개 제한

    logger.info(
        "product_registration_start",
        user_message=f"상품 등록 시작 — 총 {len(records)}개 (동시 처리 3개)",
        total=len(records),
    )

    async def _bounded(rec: dict) -> dict:
        async with semaphore:
            return await _service.register_product(rec)

    results = await asyncio.gather(
        *[_bounded(r) for r in records],
        return_exceptions=True,
    )

    succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]
    failed    = [r for r in results if not (isinstance(r, dict) and r.get("success"))]

    logger.info(
        "product_registration_complete",
        user_message=f"등록 완료 — 성공 {len(succeeded)}개 / 실패 {len(failed)}개",
        total=len(records),
        succeeded=len(succeeded),
        failed=len(failed),
    )

    if failed:
        for r in failed:
            err = r.get("error", str(r)) if isinstance(r, dict) else str(r)
            name = r.get("product_name", "?") if isinstance(r, dict) else "?"
            logger.warning(
                "product_registration_failed",
                user_message=f"실패: {name} — {err}",
                product_name=name,
                error=err,
            )

    summary = f"**{len(succeeded)}개 상품 등록 완료**"
    if failed:
        summary += f"\n실패: {len(failed)}개"

    return Command(
        update={
            "messages": [AIMessage(content=summary)],
            "logs": logger.get_user_logs(),
            "file_records": None,
            "product_registration_results": {
                "succeeded": len(succeeded),
                "failed": len(failed),
                "details": [
                    r if isinstance(r, dict) else {"error": str(r)}
                    for r in results
                ],
            },
            "status": "completed",
        },
        goto=END,
    )
