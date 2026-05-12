from datetime import datetime, timezone

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from ...core.llm_factory import get_llm
from ...config.settings import settings
from .state import FileUploadState
from .prompts import get_system_prompt
from .tools import register_personas_tool, register_products_tool

_TOOLS = [register_personas_tool, register_products_tool]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_node(state: FileUploadState, config: RunnableConfig) -> dict:
    """매 요청마다 task-scope 필드를 리셋. messages와 file_records는 건드리지 않음."""
    return {
        "status": "running",
        "error": None,
        "error_details": None,
        "logs": [],
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


async def file_upload_agent_node(state: FileUploadState, config: RunnableConfig):
    sample = (state.get("file_records") or [])[:2]
    model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    llm = get_llm(model_name, temperature=0)
    agent = create_agent(
        model=llm,
        tools=_TOOLS,
        system_prompt=get_system_prompt(sample),
    )
    return await agent.ainvoke(state, config)
