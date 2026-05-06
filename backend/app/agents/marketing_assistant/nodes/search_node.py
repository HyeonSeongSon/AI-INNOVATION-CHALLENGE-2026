from ..state import MarketingAssistantState
from ....core.llm_factory import get_llm
from ....core.logging import get_logger
from ....config.settings import settings
from langgraph.graph import END
from ...tools.search_tools import (
    get_all_personas,
    search_personas_by_text,
    get_persona_by_id,
    get_products_by_tag,
    get_products_by_brand,
    get_all_brands,
    get_all_categories,
    get_all_message_types,
)
from ...tools.prompts.search_tools_prompt import build_search_node_prompt
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage
from langgraph.types import Command

_logger = get_logger("search_node")

_TOOLS = [get_all_personas, search_personas_by_text, get_persona_by_id, get_products_by_tag, get_products_by_brand, get_all_brands, get_all_categories, get_all_message_types]
_TOOL_MAP = {t.name: t for t in _TOOLS}


async def search_node(state: MarketingAssistantState, config: RunnableConfig):
    try:
        messages = state.get("messages", [])
        model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
        llm = get_llm(model_name, temperature=0)
        llm_with_tools = llm.bind_tools(_TOOLS)

        # LLM이 tool call 여부 결정
        response = await llm_with_tools.ainvoke(build_search_node_prompt(messages))

        _logger.info(
            "search_node_llm_response",
            has_tool_calls=bool(response.tool_calls),
            tool_calls=[tc["name"] for tc in response.tool_calls] if response.tool_calls else [],
        )

        # tool call이 있으면 실행 후 최종 응답 생성
        if response.tool_calls:
            tool_messages = []
            for tc in response.tool_calls:
                tool = _TOOL_MAP.get(tc["name"])
                if tool:
                    result = await tool.ainvoke(tc["args"])
                    tool_messages.append(
                        ToolMessage(content=str(result), tool_call_id=tc["id"])
                    )

            final_response = await llm.ainvoke(messages + [response] + tool_messages)
            final_response.name = "search_node"
            return Command(goto=END, update={"messages": [response] + tool_messages + [final_response]})

        response.name = "search_node"
        return Command(goto=END, update={"messages": [response]})

    except Exception as e:
        _logger.error("search_node_failed", error_type=type(e).__name__, error_message=str(e), exc_info=True)
        raise
