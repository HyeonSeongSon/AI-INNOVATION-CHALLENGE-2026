from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing import Literal
from ...core.llm_factory import get_llm
from ...config.settings import settings
from .state import CRMMessageAgentState
from .prompts.supervisor_prompt import build_supervisor_prompt, build_final_answer_prompt
from ..tools.handoff_tools import create_handoff_messages
from ..tools.search_tools import (
    get_all_personas,
    search_personas_by_filter,
    get_persona_by_id,
    get_products_by_tag,
    get_products_by_brand,
    get_all_brands,
    get_all_categories,
    get_all_message_types,
)

class RouteDecision(BaseModel):
    next: Literal["search_agent", "recommend_product_agent", "generate_message_agent", "data_registration_agent", "FINISH"] = Field(
        description="다음 작업을 수행할 에이전트를 선택하거나, 완료됐으면 FINISH"
    )
    reason: str = Field(description="선택한 이유")


_HANDOFF_TOOL_NAMES = {
    "handoff_to_search_agent",
    "handoff_to_recommend_product_agent",
    "handoff_to_generate_message_agent",
    "handoff_to_data_registration_agent",
    "transfer_back_to_supervisor",
}

def _filter_handoff_messages(messages: list) -> list:
    handoff_tool_call_ids = set()
    filtered = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            handoff_ids = {tc["id"] for tc in msg.tool_calls if tc["name"] in _HANDOFF_TOOL_NAMES}
            if handoff_ids:
                handoff_tool_call_ids |= handoff_ids
                continue
        if isinstance(msg, ToolMessage) and msg.tool_call_id in handoff_tool_call_ids:
            continue
        filtered.append(msg)
    return filtered



_SEARCH_TOOLS = [
    get_all_personas,
    search_personas_by_filter,
    get_persona_by_id,
    get_products_by_tag,
    get_products_by_brand,
    get_all_brands,
    get_all_categories,
    get_all_message_types
]


async def supervisor_agent(state: CRMMessageAgentState, config: RunnableConfig):
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=0)
    messages = state.get("messages", [])

    decision = await llm.with_structured_output(RouteDecision).ainvoke(
        build_supervisor_prompt(messages)
    )

    if decision.next == "FINISH":
        final_answer = await llm.ainvoke(build_final_answer_prompt(messages))
        return {"messages": [final_answer]}

    return Command(goto=decision.next)

async def search_agent(state: CRMMessageAgentState, config: RunnableConfig):
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=0.7)
    agent = create_agent(
        model=llm,
        tools=_SEARCH_TOOLS,
        system_prompt=""
    )
    filtered_messages = _filter_handoff_messages(state.get("messages", []))
    result = await agent.ainvoke({"messages": filtered_messages}, config)
    ai_msg, tool_msg = create_handoff_messages("search_agent")
    return Command(
        goto="supervisor",
        update={"messages": result.get("messages", []) + [ai_msg, tool_msg]},
    )


def make_recommend_product_node(graph):
    async def recommend_product_agent(state: CRMMessageAgentState, config: RunnableConfig):
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        sub_config = {**config, "configurable": {**config.get("configurable", {}), "thread_id": f"{thread_id}:recommend"}} if thread_id else config
        subgraph_input = {
            "messages": state.get("messages", []),
            "active_persona_id": state.get("intermediate", {}).get("active_persona_id"),
        }
        result = await graph.ainvoke(subgraph_input, sub_config)
        ai_msg, tool_msg = create_handoff_messages("recommend_product_agent")
        return Command(
            goto="supervisor",
            update={
                "messages": result.get("messages", []) + [ai_msg, tool_msg],
                "intermediate": {
                    **state.get("intermediate", {}),
                    "recommended_products": result.get("recommended_products", []),
                    "active_persona_id": result.get("active_persona_id"),
                },
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return recommend_product_agent


def make_generate_message_node(graph):
    async def generate_message_agent(state: CRMMessageAgentState, config: RunnableConfig):
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        sub_config = {**config, "configurable": {**config.get("configurable", {}), "thread_id": f"{thread_id}:generate_message"}} if thread_id else config
        subgraph_input = {
            "messages": _filter_handoff_messages(state.get("messages", [])),
        }
        result = await graph.ainvoke(subgraph_input, sub_config)
        ai_msg, tool_msg = create_handoff_messages("generate_message_agent")
        return Command(
            goto="supervisor",
            update={
                "messages": result.get("messages", []) + [ai_msg, tool_msg],
                "intermediate": {
                    **state.get("intermediate", {}),
                    "generated_tasks": result.get("generated_tasks", []),
                },
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return generate_message_agent


def make_data_registration_node(graph):
    async def data_registration_agent(state: CRMMessageAgentState, config: RunnableConfig):
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        sub_config = {**config, "configurable": {**config.get("configurable", {}), "thread_id": f"{thread_id}:data_registration"}} if thread_id else config
        subgraph_input = {
            "messages": _filter_handoff_messages(state.get("messages", [])),
            "file_records": state.get("file_records"),
        }
        result = await graph.ainvoke(subgraph_input, sub_config)
        ai_msg, tool_msg = create_handoff_messages("data_registration_agent")
        return Command(
            goto="supervisor",
            update={
                "messages": result.get("messages", []) + [ai_msg, tool_msg],
                "file_records": None,
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return data_registration_agent
