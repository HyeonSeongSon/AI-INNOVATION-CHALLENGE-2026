import json
from datetime import datetime, timezone
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from ...core.llm_factory import get_llm
from ...core.logging import AgentLogger
from ...config.settings import settings
from .state import DataRegistrationState
from .prompts.system_prompts import get_base_system_prompt
from .tools import register_personas_tool, register_products_tool, create_persona_from_text_tool

_TOOLS = [register_personas_tool, register_products_tool, create_persona_from_text_tool]


@lru_cache(maxsize=8)
def _get_data_agent(model_name: str, has_records: bool):
    llm = get_llm(model_name, temperature=0)
    return create_agent(
        model=llm,
        tools=_TOOLS,
        system_prompt=get_base_system_prompt(has_records),
        state_schema=DataRegistrationState,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_node(state: DataRegistrationState, config: RunnableConfig) -> dict:
    """매 요청마다 task-scope 필드를 리셋. messages와 file_records는 건드리지 않음."""
    logger = AgentLogger({**state, "logs": []}, node_name="init_node", agent_name="data_registration_agent")
    logger.info("agent_started", user_message="[init] 에이전트 시작")
    return {
        "status": "running",
        "error": None,
        "error_details": None,
        "logs": logger.get_user_logs(),
        "step": 0,
        "node_history": ["init"],
        "current_node": "init",
        "last_node": None,
        "is_interrupted": False,
        "decisions": {},
        "intermediate": {},
        "start_time": _now_iso(),
        "end_time": None,
        "duration_ms": None,
    }


async def data_registration_agent_node(state: DataRegistrationState, config: RunnableConfig):
    node_name = "data_registration_agent"
    logger = AgentLogger(state, node_name=node_name, agent_name="data_registration_agent")
    logger.info("data_registration_started", user_message=f"[{node_name}] 데이터 등록 시작")
    step = state.get("step", 0) + 1
    base = {
        "step": step,
        "current_node": node_name,
        "last_node": state.get("current_node"),
        "node_history": state.get("node_history", []) + [node_name],
    }
    try:
        sample = (state.get("file_records") or [])[:2]
        has_records = bool(sample)
        model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
        agent = _get_data_agent(model_name, has_records)
        sample_msg = SystemMessage(
            content=f"샘플 레코드:\n{json.dumps(sample, ensure_ascii=False, indent=2)}"
        )
        augmented_state = {**state, "messages": [sample_msg] + list(state.get("messages", []))}
        result = await agent.ainvoke(augmented_state, config)

        end_time = _now_iso()
        start_time = state.get("start_time")
        duration_ms = None
        if start_time:
            duration_ms = (datetime.fromisoformat(end_time) - datetime.fromisoformat(start_time)).total_seconds() * 1000

        final_status = result.get("status", "completed")
        if final_status in ("failed", "error", "partial_failure"):
            logger.error(
                "data_registration_inner_failed",
                user_message=f"[{node_name}] 데이터 등록 중 내부 오류가 발생했습니다.",
                inner_status=final_status,
            )
            return {
                **result,
                **base,
                "status": final_status,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "logs": logger.get_user_logs(),
            }

        logger.info(
            "data_registration_done",
            user_message=f"[{node_name}] 데이터 등록 완료 ({duration_ms:.0f}ms)" if duration_ms is not None else f"[{node_name}] 데이터 등록 완료",
            duration_ms=duration_ms,
        )
        return {
            **result,
            **base,
            "status": "completed",
            "end_time": end_time,
            "duration_ms": duration_ms,
            "logs": logger.get_user_logs(),
        }
    except Exception as e:
        logger.error("data_registration_error", user_message=f"[{node_name}] 오류가 발생했습니다.", error_type=type(e).__name__, exc_info=True)
        return {
            **base,
            "status": "failed",
            "error": "데이터 등록 중 오류가 발생했습니다.",
            "error_details": {"node": node_name},
            "logs": logger.get_user_logs(),
        }
