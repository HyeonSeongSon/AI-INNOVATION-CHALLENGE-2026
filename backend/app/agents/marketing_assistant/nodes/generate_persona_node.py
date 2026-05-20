import asyncio
from ..state import MarketingAssistantState
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from langgraph.types import Command
from langgraph.graph import END
from ...shared.persona.generate_persona_and_query import generate_structured_persona_info, generate_search_query
from ....core.llm_factory import get_llm
from ....config.settings import settings
from ....core.logging import get_logger

_logger = get_logger("generate_persona_node")

async def generate_persona_node(state: MarketingAssistantState, config: RunnableConfig):
    persona_client = config["configurable"]["services"].persona_client
    messages = state.get("messages")
    llm = get_llm(settings.chatgpt_model_name, temperature=0.3)

    try:
        structured_persona, raw_queries = await asyncio.gather(
            generate_structured_persona_info(messages, llm),
            generate_search_query(messages, llm),
        )
    except Exception as e:
        _logger.error("generate_persona_node_failed", error=str(e), exc_info=True)
        return Command(update={"status": "error", "error_message": str(e)}, goto=END)

    # DB 저장
    persona_id = await persona_client.save_persona(structured_persona)
    await persona_client.save_product_search_query(persona_id, raw_queries)

    # state 형식으로 변환
    search_queries = {
        "user_need_query": raw_queries["need"],
        "user_preference_query": raw_queries["preference"],
        "retrieval": raw_queries["retrieval"],
        "persona": raw_queries["persona"],
    }

    persona_summary = structured_persona.get("persona_summary") or "요약 없음"
    message = (
        f"페르소나 저장 완료 (persona_id: {persona_id})\n\n"
        f"## 페르소나 요약\n{persona_summary}\n\n"
        f"## 생성된 검색 쿼리\n"
        f"- 니즈 쿼리: {raw_queries['need']}\n"
        f"- 선호 쿼리: {raw_queries['preference']}\n"
        f"- 검색 쿼리: {raw_queries['retrieval']}\n"
        f"- 페르소나 쿼리: {raw_queries['persona']}"
    )

    return Command(
        update={
            "messages": [AIMessage(content=message)],
            "search_queries": search_queries,
        },
        goto=END,
    )
