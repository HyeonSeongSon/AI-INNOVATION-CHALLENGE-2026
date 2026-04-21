import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.graph import END

from ..state import MarketingAssistantState
from ..services.generate_persona_and_query import (
    generate_structured_persona_info,
    generate_search_query,
)
from ..services.persona_client import PersonaClient
from ....core.llm_factory import get_llm
from ....config.settings import settings
from ....core.logging import get_logger

logger = get_logger("bulk_persona_node")

_persona_client = PersonaClient()


async def _process_one(index: int, record: dict, llm) -> dict:
    """단일 레코드 처리 — generate_persona_node와 동일한 파이프라인"""
    try:
        messages = [HumanMessage(content=json.dumps(record, ensure_ascii=False, indent=2))]
        structured_persona = await generate_structured_persona_info(messages, llm)
        persona_id = await _persona_client.save_persona(structured_persona)
        raw_queries = await generate_search_query(messages, llm)
        await _persona_client.save_product_search_query(persona_id, raw_queries)
        return {
            "index": index,
            "success": True,
            "persona_id": persona_id,
            "persona_name": structured_persona.get("name"),
        }
    except Exception as e:
        logger.error("bulk_persona_record_failed", index=index, error=str(e))
        return {"index": index, "success": False, "error": str(e)}


async def bulk_persona_node(state: MarketingAssistantState, config: RunnableConfig):
    """파일에서 파싱된 레코드를 병렬로 처리해 페르소나를 일괄 생성."""
    records = state.get("file_records") or []
    llm = get_llm(settings.chatgpt_model_name, temperature=0.3)
    semaphore = asyncio.Semaphore(5)

    async def _bounded(i: int, rec: dict):
        async with semaphore:
            return await _process_one(i, rec, llm)

    results = await asyncio.gather(*[_bounded(i, r) for i, r in enumerate(records)])

    succeeded = [r for r in results if r["success"]]
    failed    = [r for r in results if not r["success"]]

    summary = f"**{len(succeeded)}명 페르소나 생성 완료**"
    if failed:
        lines = "\n".join(
            f"- {r['index'] + 1}번째 레코드: {r['error']}" for r in failed
        )
        summary += f" ({len(failed)}명 실패)\n\n**실패 목록:**\n{lines}"
    if succeeded:
        lines = "\n".join(
            f"- {r.get('persona_name') or '(이름 없음)'} `{r['persona_id']}`"
            for r in succeeded
        )
        summary += f"\n\n**생성된 페르소나:**\n{lines}"

    logger.info(
        "bulk_persona_node_done",
        total=len(results),
        succeeded=len(succeeded),
        failed=len(failed),
    )

    return Command(
        update={
            "messages": [AIMessage(content=summary)],
            "file_records": None,   # 다음 턴 오염 방지
            "status": "completed",
        },
        goto=END,
    )
