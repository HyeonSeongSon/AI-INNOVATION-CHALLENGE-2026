
from ..state import SupervisorState
from ....core.llm_factory import get_llm
from ....core.logging import get_logger
from ..services.supervisor import Supervisor
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.constants import END

import os

_supervisor = Supervisor()
logger = get_logger("supervisor_node")

async def supervisor_node(state: SupervisorState, config: RunnableConfig):
    try:
        messages = state.get("messages")
        model_name = config.get("configurable", {}).get("model", os.getenv("CHATGPT_MODEL_NAME"))
        llm = get_llm(model_name, temperature=0)
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
            # input: CRMState가 공유 key로 읽어가는 사용자 원본 텍스트
            # messages[-1]이 노드 결과일 수 있으므로 마지막 HumanMessage를 사용
            last_human = next(
                (m for m in reversed(messages) if isinstance(m, HumanMessage)),
                messages[-1],
            )
            user_input = last_human.content if hasattr(last_human, "content") else str(last_human)
            return Command(
                goto="crm_node",
                update={
                    "input": user_input,
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