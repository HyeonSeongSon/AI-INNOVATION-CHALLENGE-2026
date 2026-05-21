from fastapi import APIRouter, Request

from a2a.models import AgentCard, AgentSkill, DataPart, Task, TaskSendRequest, TaskStatus
from a2a.serialization import deserialize_messages, serialize_messages
from app.config.settings import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/a2a/data-registration", tags=["A2A: Data Registration Agent"])

_logger = get_logger("data_registration_agent.a2a")


@router.get("/.well-known/agent.json", response_model=AgentCard)
async def agent_card():
    return AgentCard(
        name="data_registration_agent",
        description="페르소나 및 상품 데이터를 DB에 등록하는 에이전트 (파일 일괄 등록 및 자연어 단건 등록 지원)",
        url=f"{settings.data_registration_agent_url}/a2a/data-registration",
        skills=[
            AgentSkill(
                id="register",
                name="데이터 등록",
                description="페르소나 특성 텍스트 또는 파일 레코드(file_records)를 받아 DB에 등록합니다",
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
        "file_records": data.get("file_records"),
    }
    config = {
        "configurable": {"thread_id": request.sessionId or request.id, "services": req.app.state.services},
        "recursion_limit": settings.langgraph_recursion_limit,
    }

    _logger.info("a2a_task_received", task_id=request.id, session_id=request.sessionId)

    try:
        graph = req.app.state.graph
        result = await graph.ainvoke(subgraph_input, config)

        status = TaskStatus.COMPLETED if result.get("status") == "completed" else TaskStatus.FAILED

        _logger.info("a2a_task_completed", task_id=request.id, status=status)

        return Task(
            id=request.id,
            sessionId=request.sessionId,
            status=status,
            artifacts=[{
                "type": "data",
                "data": {
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
            artifacts=[{"type": "data", "data": {"error": "데이터 등록 처리 중 오류가 발생했습니다.", "status": "failed"}}],
        )
