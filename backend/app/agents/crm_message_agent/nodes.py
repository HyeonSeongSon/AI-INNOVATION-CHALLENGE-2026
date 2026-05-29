import uuid
import httpx
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing import List, Literal
from a2a.client import A2AClient
from a2a.models import TaskStatus
from a2a.serialization import deserialize_messages
from ...core.llm_factory import get_llm
from ...core.llm_utils import ainvoke_with_timeout
from ...core.logging import get_logger
from ...config.settings import settings
from .state import CRMMessageAgentState
from .prompts.supervisor_prompt import build_supervisor_prompt, build_final_answer_prompt
from .prompts.summary_prompt import build_summary_prompt
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


async def maybe_summarize(state: CRMMessageAgentState, config: RunnableConfig):
    messages = state.get("messages", [])
    if len(messages) <= settings.conversation_summarize_threshold:
        return {}

    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=settings.llm_temperature_classifier)
    existing_summary = state.get("summary", "")

    try:
        response = await ainvoke_with_timeout(llm, build_summary_prompt(messages, existing_summary))
    except Exception as e:
        _logger.warning("summarize_skipped", error_type=type(e).__name__)
        return {}

    messages_to_delete = messages[:-settings.conversation_keep_messages]
    delete_ops = [RemoveMessage(id=m.id) for m in messages_to_delete]

    _logger.info(
        "conversation_summarized",
        deleted=len(messages_to_delete),
        kept=settings.conversation_keep_messages,
    )
    return {"summary": response.content, "messages": delete_ops}


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


@lru_cache(maxsize=4)
def _get_search_agent(model_name: str):
    llm = get_llm(model_name, temperature=settings.llm_temperature_generator)
    return create_agent(model=llm, tools=_SEARCH_TOOLS, system_prompt="")


async def supervisor_agent(state: CRMMessageAgentState, config: RunnableConfig):
    _logger.info("supervisor_started", node_name="supervisor_agent")

    if state.get("status") in ("failed", "partial_failure"):
        _logger.warning("supervisor_aborted_on_error", node_name="supervisor_agent")
        return {
            "messages": [AIMessage(content="처리 중 오류가 발생하여 작업을 중단합니다. 다시 시도해주세요.", name="supervisor")],
            "task_plan": [],
        }

    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model, temperature=settings.llm_temperature_classifier)
    messages = state.get("messages", [])
    task_plan = state.get("task_plan", [])
    summary = state.get("summary", "")

    # 플랜이 이미 확정된 경우: LLM 없이 결정
    if task_plan:
        completed = _get_completed_agents(messages)
        remaining = [t for t in task_plan if t not in completed]

        if not remaining:
            _logger.info("supervisor_all_done", node_name="supervisor_agent")
            try:
                final_answer = await ainvoke_with_timeout(llm, build_final_answer_prompt(messages, summary))
            except Exception as e:
                _logger.error("supervisor_final_answer_failed", error_type=type(e).__name__, node_name="supervisor_agent")
                return {"status": "failed", "error": "최종 응답 생성 실패"}
            return {"messages": [final_answer], "task_plan": []}

        next_agent = remaining[0]
        _logger.info("supervisor_deterministic_route", node_name="supervisor_agent", next=next_agent)
        return Command(goto=next_agent)

    # 첫 진입: LLM으로 전체 플랜 결정
    try:
        decision = await ainvoke_with_timeout(
            llm.with_structured_output(RouteDecision),
            build_supervisor_prompt(messages, summary, file_records=state.get("file_records"))
        )
    except Exception as e:
        # LLM이 JSON 외 텍스트를 덧붙여 파싱 실패한 경우
        _logger.warning("supervisor_routing_parse_failed", error_type=type(e).__name__, node_name="supervisor_agent")
        try:
            final_answer = await ainvoke_with_timeout(llm, build_final_answer_prompt(messages, summary))
        except Exception as e2:
            _logger.error("supervisor_final_answer_failed", error_type=type(e2).__name__, node_name="supervisor_agent")
            return {"status": "failed", "error": "최종 응답 생성 실패"}
        return {"messages": [final_answer]}

    _logger.info("supervisor_plan_decided", node_name="supervisor_agent",
                 task_plan=decision.task_plan, reason=decision.reason)

    if not decision.task_plan:
        try:
            final_answer = await ainvoke_with_timeout(llm, build_final_answer_prompt(messages, summary))
        except Exception as e:
            _logger.error("supervisor_final_answer_failed", error_type=type(e).__name__, node_name="supervisor_agent")
            return {"status": "failed", "error": "최종 응답 생성 실패"}
        return {"messages": [final_answer]}

    return Command(
        goto=decision.task_plan[0],
        update={"task_plan": decision.task_plan},
    )

async def search_agent(state: CRMMessageAgentState, config: RunnableConfig):
    _logger.info("search_agent_started", node_name="search_agent")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    agent = _get_search_agent(model)
    filtered_messages = _filter_handoff_messages(state.get("messages", []))
    try:
        result = await agent.ainvoke({"messages": filtered_messages}, config)
    except Exception as e:
        _logger.error("search_agent_failed", error_type=type(e).__name__, exc_info=True)
        return Command(goto="supervisor", update={"status": "failed", "error": "에이전트 실행 실패"})
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
            _logger.error("recommend_product_agent_failed", node_name="recommend_product_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "logs": ["[에러] recommend_product_agent: 호출 실패"],
                    "messages": [AIMessage(content="상품 추천 에이전트 호출에 실패했습니다.", name="recommend_product_agent")],
                },
            )

        if task.status == TaskStatus.FAILED:
            error_detail = (
                task.artifacts[0].get("data", {}).get("error", "알 수 없는 오류")
                if task.artifacts
                else "알 수 없는 오류"
            )
            _logger.error("recommend_product_agent_task_failed", node_name="recommend_product_agent", error=error_detail)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "에이전트 처리 중 오류가 발생했습니다.",
                    "logs": ["[오류] recommend_product_agent 실패"],
                    "messages": [AIMessage(content="상품 추천 에이전트가 실패했습니다.", name="recommend_product_agent")],
                },
            )

        if task.status != TaskStatus.COMPLETED or not task.artifacts:
            _logger.error("recommend_product_agent_task_incomplete", node_name="recommend_product_agent", task_status=str(task.status))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "서브에이전트가 비정상 종료되었습니다.",
                    "error_details": {"node": "recommend_product_agent", "task_status": str(task.status)},
                    "logs": ["[오류] recommend_product_agent 비정상 종료"],
                    "messages": [AIMessage(content="상품 추천 에이전트가 비정상 종료되었습니다.", name="recommend_product_agent")],
                },
            )

        result = task.artifacts[0].get("data", {})

        _logger.info("recommend_product_agent_done", node_name="recommend_product_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("recommend_product_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="recommend_product_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "error": "메시지 역직렬화 실패",
                    "task_plan": [],
                    "logs": ["[에러] recommend_product_agent: 메시지 역직렬화 실패"],
                    "messages": [AIMessage(content="상품 추천 에이전트 응답 처리에 실패했습니다.", name="recommend_product_agent")],
                },
            )
        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "recommended_products": result.get("recommended_products", []),
                "active_persona_id": result.get("active_persona_id"),
                "status": result.get("status"),
                "logs": result.get("logs", []),
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
            _logger.error("generate_message_agent_failed", node_name="generate_message_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "logs": ["[에러] generate_message_agent: 호출 실패"],
                    "messages": [AIMessage(content="메시지 생성 에이전트 호출에 실패했습니다.", name="generate_message_agent")],
                },
            )

        if task.status == TaskStatus.FAILED:
            error_detail = (
                task.artifacts[0].get("data", {}).get("error", "알 수 없는 오류")
                if task.artifacts
                else "알 수 없는 오류"
            )
            _logger.error("generate_message_agent_task_failed", node_name="generate_message_agent", error=error_detail)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "에이전트 처리 중 오류가 발생했습니다.",
                    "logs": ["[오류] generate_message_agent 실패"],
                    "messages": [AIMessage(content="메시지 생성 에이전트가 실패했습니다.", name="generate_message_agent")],
                },
            )

        if task.status != TaskStatus.COMPLETED or not task.artifacts:
            _logger.error("generate_message_agent_task_incomplete", node_name="generate_message_agent", task_status=str(task.status))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "서브에이전트가 비정상 종료되었습니다.",
                    "error_details": {"node": "generate_message_agent", "task_status": str(task.status)},
                    "logs": ["[오류] generate_message_agent 비정상 종료"],
                    "messages": [AIMessage(content="메시지 생성 에이전트가 비정상 종료되었습니다.", name="generate_message_agent")],
                },
            )

        result = task.artifacts[0].get("data", {})

        _logger.info("generate_message_agent_done", node_name="generate_message_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("generate_message_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="generate_message_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "error": "메시지 역직렬화 실패",
                    "task_plan": [],
                    "logs": ["[에러] generate_message_agent: 메시지 역직렬화 실패"],
                    "messages": [AIMessage(content="메시지 생성 에이전트 응답 처리에 실패했습니다.", name="generate_message_agent")],
                },
            )
        internal_status = result.get("status")

        if internal_status in ("failed", "partial_failure"):
            _logger.warning(
                "generate_message_agent_internal_failure",
                node_name="generate_message_agent",
                internal_status=internal_status,
            )
            return Command(
                goto="supervisor",
                update={
                    "messages": messages + [ai_msg, tool_msg],
                    "generated_tasks": result.get("generated_tasks", []),
                    "status": "failed",
                    "task_plan": [],
                    "logs": result.get("logs", []),
                },
            )

        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "generated_tasks": result.get("generated_tasks", []),
                "status": internal_status,
                "logs": result.get("logs", []),
            },
        )
    return generate_message_agent


def make_data_registration_node(client: A2AClient):
    async def data_registration_agent(state: CRMMessageAgentState, config: RunnableConfig):
        _logger.info("data_registration_agent_started", node_name="data_registration_agent")
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        session_id = f"{thread_id}:data_registration" if thread_id else str(uuid.uuid4())

        file_records = state.get("file_records")
        a2a_timeout = httpx.Timeout(connect=settings.http_timeout_stream_connect, read=None, write=None, pool=settings.http_timeout_stream_pool) if file_records else None
        try:
            task = await client.send_task(session_id, {
                "messages": _filter_handoff_messages(state.get("messages", [])),
                "file_records": file_records,
                "user_id": (config or {}).get("configurable", {}).get("user_id"),
            }, timeout=a2a_timeout)
        except Exception as e:
            _logger.error("data_registration_agent_failed", node_name="data_registration_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "logs": ["[에러] data_registration_agent: 호출 실패"],
                    "messages": [AIMessage(content="데이터 등록 에이전트 호출에 실패했습니다.", name="data_registration_agent")],
                },
            )

        if task.status == TaskStatus.FAILED:
            error_detail = (
                task.artifacts[0].get("data", {}).get("error", "알 수 없는 오류")
                if task.artifacts
                else "알 수 없는 오류"
            )
            _logger.error("data_registration_agent_task_failed", node_name="data_registration_agent", error=error_detail)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "에이전트 처리 중 오류가 발생했습니다.",
                    "logs": ["[오류] data_registration_agent 실패"],
                    "messages": [AIMessage(content="데이터 등록 에이전트가 실패했습니다.", name="data_registration_agent")],
                },
            )

        if task.status != TaskStatus.COMPLETED or not task.artifacts:
            _logger.error("data_registration_agent_task_incomplete", node_name="data_registration_agent", task_status=str(task.status))
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "task_plan": [],
                    "error": "서브에이전트가 비정상 종료되었습니다.",
                    "error_details": {"node": "data_registration_agent", "task_status": str(task.status)},
                    "logs": ["[오류] data_registration_agent 비정상 종료"],
                    "messages": [AIMessage(content="데이터 등록 에이전트가 비정상 종료되었습니다.", name="data_registration_agent")],
                },
            )

        result = task.artifacts[0].get("data", {})

        _logger.info("data_registration_agent_done", node_name="data_registration_agent", status=result.get("status"))
        ai_msg, tool_msg = create_handoff_messages("data_registration_agent")
        try:
            messages = deserialize_messages(result.get("messages", []))
        except Exception as e:
            _logger.error("deserialize_messages_failed", node_name="data_registration_agent", error_type=type(e).__name__)
            return Command(
                goto="supervisor",
                update={
                    "status": "failed",
                    "error": "메시지 역직렬화 실패",
                    "task_plan": [],
                    "logs": ["[에러] data_registration_agent: 메시지 역직렬화 실패"],
                    "messages": [AIMessage(content="데이터 등록 에이전트 응답 처리에 실패했습니다.", name="data_registration_agent")],
                },
            )
        return Command(
            goto="supervisor",
            update={
                "messages": messages + [ai_msg, tool_msg],
                "file_records": None,
                "status": result.get("status"),
                "logs": result.get("logs", []),
            },
        )
    return data_registration_agent
