from fastapi import APIRouter, Request

from a2a.models import AgentCard, AgentSkill, DataPart, Task, TaskSendRequest, TaskStatus
from a2a.serialization import deserialize_messages, serialize_messages
from app.config.settings import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/a2a/generate-message", tags=["A2A: Generate Message Agent"])

_logger = get_logger("generate_message_agent.a2a")


@router.get("/.well-known/agent.json", response_model=AgentCard)
async def agent_card():
    return AgentCard(
        name="generate_message_agent",
        description="페르소나와 상품 정보를 기반으로 CRM 메시지를 생성하고 품질을 검사하는 에이전트",
        url=f"{settings.generate_message_agent_url}/a2a/generate-message",
        skills=[
            AgentSkill(
                id="generate",
                name="CRM 메시지 생성",
                description="상품·페르소나 조합으로 문자, 앱푸시 등 CRM 메시지를 생성하고 품질 검사를 수행합니다",
            )
        ],
    )


@router.post("/tasks/send", response_model=Task)
async def send_task(request: TaskSendRequest, req: Request):
    data = next(
        (p.data for p in request.message.parts if isinstance(p, DataPart)),
        {},
    )

    messages = deserialize_messages(data.get("messages", []))
    subgraph_input = {
        "messages": messages,
        **({"active_persona_id": data["active_persona_id"]} if data.get("active_persona_id") else {}),
    }
    config = {"configurable": {"thread_id": request.sessionId or request.id}}

    _logger.info("a2a_task_received", task_id=request.id, session_id=request.sessionId,
                 active_persona_id=data.get("active_persona_id"))

    try:
        graph = req.app.state.graph
        result = await graph.ainvoke(subgraph_input, config)

        agent_status = result.get("status")
        status = TaskStatus.COMPLETED if agent_status == "completed" else TaskStatus.FAILED

        _logger.info("a2a_task_completed", task_id=request.id, status=status)

        return Task(
            id=request.id,
            sessionId=request.sessionId,
            status=status,
            artifacts=[{
                "type": "data",
                "data": {
                    "generated_tasks": result.get("generated_tasks", []),
                    "messages": serialize_messages(result.get("messages", [])),
                    "logs": result.get("logs", []),
                    "status": result.get("status"),
                },
            }],
        )

    except Exception as e:
        _logger.error("a2a_task_failed", task_id=request.id, error=str(e), exc_info=True)
        return Task(
            id=request.id,
            sessionId=request.sessionId,
            status=TaskStatus.FAILED,
            artifacts=[{"type": "data", "data": {"error": str(e), "status": "failed"}}],
        )
