from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from ...core.llm_factory import get_llm
from ...config.settings import settings
from .state import CRMMessageAgentState
from ..recommend_product_agent.workflow import build_workflow as build_recommend_workflow
from ..generate_message_agent.workflow import build_workflow as build_generate_message_workflow
from .prompts.supervisor_prompt import get_supervisor_system_prompt
from ..tools.handoff_tools import (
    handoff_to_generate_message_agent,
    handoff_to_recommend_product_agent,
    handoff_to_search_agent,
    create_handoff_messages,
)
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

_SUPERVISOR_TOOLS = [
    handoff_to_generate_message_agent, 
    handoff_to_recommend_product_agent, 
    handoff_to_search_agent
]
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

_recommend_graph = build_recommend_workflow()
_generate_message_graph = build_generate_message_workflow()

async def supervisor_agent(state: CRMMessageAgentState, config: RunnableConfig):
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=0.7)
    supervisor = create_agent(
        model=llm,
        tools=_SUPERVISOR_TOOLS,
        system_prompt=get_supervisor_system_prompt()
    )
    return await supervisor.ainvoke(state, config)

async def search_agent(state: CRMMessageAgentState, config: RunnableConfig):
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=0.7)
    agent = create_agent(
        model=llm,
        tools=_SEARCH_TOOLS,
        system_prompt=""
    )
    result = await agent.ainvoke(state, config)
    ai_msg, tool_msg = create_handoff_messages("search_agent")
    return Command(
        goto="supervisor",
        update={"messages": result.get("messages", []) + [ai_msg, tool_msg]},
    )

async def recommend_product_agent(state: CRMMessageAgentState, config: RunnableConfig):
    subgraph_input = {
        "messages": state.get("messages", []),
        "active_persona_id": state.get("intermediate", {}).get("active_persona_id"),
    }
    result = await _recommend_graph.ainvoke(subgraph_input, config)
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

async def generate_message_agent(state: CRMMessageAgentState, config: RunnableConfig):
    subgraph_input = {
        "messages": state.get("messages", []),
    }
    result = await _generate_message_graph.ainvoke(subgraph_input, config)
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
