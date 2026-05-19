import uuid
import httpx

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing import List, Literal
from a2a.client import A2AClient
from a2a.serialization import deserialize_messages
from ...core.llm_factory import get_llm
from ...core.logging import get_logger
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

_logger = get_logger("crm_message_agent")

_ValidAgent = Literal[
    "search_agent", "recommend_product_agent",
    "generate_message_agent", "data_registration_agent"
]

class RouteDecision(BaseModel):
    task_plan: List[_ValidAgent] = Field(
        description="수행해야 할 에이전트 순서 목록. 완료됐거나 할 작업이 없으면 빈 리스트."
    )
    reason: str = Field(description="선택한 이유")


_HANDOFF_TOOL_NAMES = {
    "handoff_to_search_agent",
    "handoff_to_recommend_product_agent",
    "handoff_to_generate_message_agent",
    "handoff_to_data_registration_agent",
    "transfer_back_to_supervisor",
}

_AGENT_NAMES = {
    "search_agent", "recommend_product_agent",
    "generate_message_agent", "data_registration_agent",
}

def _get_completed_agents(messages: list) -> set:
    return {
        msg.name
        for msg in messages
        if isinstance(msg, AIMessage) and msg.name in _AGENT_NAMES
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
    _logger.info("supervisor_started", node_name="supervisor_agent")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=0)
    messages = state.get("messages", [])
    task_plan = state.get("task_plan", [])

    # 플랜이 이미 확정된 경우: LLM 없이 결정
    if task_plan:
        completed = _get_completed_agents(messages)
        remaining = [t for t in task_plan if t not in completed]

        if not remaining:
            _logger.info("supervisor_all_done", node_name="supervisor_agent")
            final_answer = await llm.ainvoke(build_final_answer_prompt(messages))
            return {"messages": [final_answer], "task_plan": []}

        next_agent = remaining[0]
        _logger.info("supervisor_deterministic_route", node_name="supervisor_agent", next=next_agent)
        return Command(goto=next_agent)

    # 첫 진입: LLM으로 전체 플랜 결정
    try:
        decision = await llm.with_structured_output(RouteDecision).ainvoke(
            build_supervisor_prompt(messages)
        )
    except Exception as e:
        # LLM이 JSON 외 텍스트를 덧붙여 파싱 실패한 경우
        _logger.warning("supervisor_routing_parse_failed", error=str(e), node_name="supervisor_agent")
        final_answer = await llm.ainvoke(build_final_answer_prompt(messages))
        return {"messages": [final_answer]}

    _logger.info("supervisor_plan_decided", node_name="supervisor_agent",
                 task_plan=decision.task_plan, reason=decision.reason)

    if not decision.task_plan:
        final_answer = await llm.ainvoke(build_final_answer_prompt(messages))
        return {"messages": [final_answer]}

    return Command(
        goto=decision.task_plan[0],
        update={"task_plan": decision.task_plan},
    )

async def search_agent(state: CRMMessageAgentState, config: RunnableConfig):
    _logger.info("search_agent_started", node_name="search_agent")
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
    _logger.info("search_agent_done", node_name="search_agent")
    return Command(
        goto="supervisor",
        update={"messages": result.get("messages", []) + [ai_msg, tool_msg]},
    )


def make_recommend_product_node(client: A2AClient):
    async def recommend_product_agent(state: CRMMessageAgentState, config: RunnableConfig):
        _logger.info("recommend_product_agent_started", node_name="recommend_product_agent")
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        session_id = f"{thread_id}:recommend" if thread_id else str(uuid.uuid4())

        try:
            task = await client.send_task(session_id, {
                "messages": _filter_handoff_messages(state.get("messages", [])),
                "active_persona_id": state.get("active_persona_id"),
            })
        except Exception as e:
            _logger.error("recommend_product_agent_failed", node_name="recommend_product_agent", error=str(e))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": str(e),
                    "logs": state.get("logs", []) + [f"[에러] recommend_product_agent: {e}"],
                    "messages": [AIMessage(content=f"상품 추천 에이전트 호출에 실패했습니다: {e}", name="recommend_product_agent")],
                },
            )

        if not task.artifacts:
            _logger.error("recommend_product_agent_empty_artifacts", node_name="recommend_product_agent")
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "빈 artifacts 응답",
                    "logs": state.get("logs", []) + ["[에러] recommend_product_agent: 응답에 artifacts가 없습니다"],
                    "messages": [AIMessage(content="상품 추천 에이전트가 빈 응답을 반환했습니다.", name="recommend_product_agent")],
                },
            )

        result = task.artifacts[0]["data"]

        _logger.info("recommend_product_agent_done", node_name="recommend_product_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("recommend_product_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="recommend_product_agent", error=str(e))
            messages = []
        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "recommended_products": result.get("recommended_products", []),
                "active_persona_id": result.get("active_persona_id"),
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return recommend_product_agent


def make_generate_message_node(client: A2AClient):
    async def generate_message_agent(state: CRMMessageAgentState, config: RunnableConfig):
        _logger.info("generate_message_agent_started", node_name="generate_message_agent")
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        session_id = f"{thread_id}:generate_message" if thread_id else str(uuid.uuid4())

        try:
            task = await client.send_task(session_id, {
                "messages": _filter_handoff_messages(state.get("messages", [])),
                "active_persona_id": state.get("active_persona_id"),
            })
        except Exception as e:
            _logger.error("generate_message_agent_failed", node_name="generate_message_agent", error=str(e))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": str(e),
                    "logs": state.get("logs", []) + [f"[에러] generate_message_agent: {e}"],
                    "messages": [AIMessage(content=f"메시지 생성 에이전트 호출에 실패했습니다: {e}", name="generate_message_agent")],
                },
            )

        if not task.artifacts:
            _logger.error("generate_message_agent_empty_artifacts", node_name="generate_message_agent")
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "빈 artifacts 응답",
                    "logs": state.get("logs", []) + ["[에러] generate_message_agent: 응답에 artifacts가 없습니다"],
                    "messages": [AIMessage(content="메시지 생성 에이전트가 빈 응답을 반환했습니다.", name="generate_message_agent")],
                },
            )

        result = task.artifacts[0]["data"]

        _logger.info("generate_message_agent_done", node_name="generate_message_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("generate_message_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="generate_message_agent", error=str(e))
            messages = []
        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "generated_tasks": result.get("generated_tasks", []),
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return generate_message_agent


def make_data_registration_node(client: A2AClient):
    async def data_registration_agent(state: CRMMessageAgentState, config: RunnableConfig):
        _logger.info("data_registration_agent_started", node_name="data_registration_agent")
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        session_id = f"{thread_id}:data_registration" if thread_id else str(uuid.uuid4())

        try:
            task = await client.send_task(session_id, {
                "messages": _filter_handoff_messages(state.get("messages", [])),
                "file_records": state.get("file_records"),
            })
        except Exception as e:
            _logger.error("data_registration_agent_failed", node_name="data_registration_agent", error=str(e))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": str(e),
                    "logs": state.get("logs", []) + [f"[에러] data_registration_agent: {e}"],
                    "messages": [AIMessage(content=f"데이터 등록 에이전트 호출에 실패했습니다: {e}", name="data_registration_agent")],
                },
            )

        if not task.artifacts:
            _logger.error("data_registration_agent_empty_artifacts", node_name="data_registration_agent")
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "빈 artifacts 응답",
                    "logs": state.get("logs", []) + ["[에러] data_registration_agent: 응답에 artifacts가 없습니다"],
                    "messages": [AIMessage(content="데이터 등록 에이전트가 빈 응답을 반환했습니다.", name="data_registration_agent")],
                },
            )

        result = task.artifacts[0]["data"]

        _logger.info("data_registration_agent_done", node_name="data_registration_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("data_registration_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="data_registration_agent", error=str(e))
            messages = []
        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "file_records": None,
                "status": result.get("status"),
                "logs": state.get("logs", []) + result.get("logs", []),
            },
        )
    return data_registration_agent
