
from ..state import SupervisorState
from ....core.llm_factory import create_llm
from ....core.logging import get_logger
from ..services.supervisor import Supervisor
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.constants import END

import os

_supervisor = Supervisor()
logger = get_logger("supervisor_node")

async def supervisor_node(state: SupervisorState, config: RunnableConfig):
    try:
        messages = state.get("messages")
        model_name = config.get("configurable", {}).get("model", os.getenv("CHATGPT_MODEL_NAME"))
        llm = create_llm(model_name, temperature=0)
        decision = await _supervisor.supervisor(messages, llm)

        logger.info(
            "supervisor_decision",
            next_step=decision.next_step,
            reason=decision.reason,
        )

        # 다음 노드 결정
        if decision.next_step == "FINISH":
            return Command(goto=END)
        elif decision.next_step == "crm_node":
            # CRM subgraph 진입 시 필요한 초기 상태 설정
            # input: CRMState가 공유 key로 읽어가는 사용자 원본 텍스트
            user_input = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
            return Command(
                goto="crm_node",
                update={
                    "input": user_input,
                    "step": 0,
                    "logs": [],
                    "intermediate": {},
                    "status": "running",
                },
            )
        else:
            return Command(goto=decision.next_step)
    except Exception as e:
        logger.error(
            "supervisor_node_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise