from fastapi import APIRouter, Request

from a2a.models import AgentCard, AgentSkill, DataPart, Task, TaskSendRequest, TaskStatus
from a2a.serialization import deserialize_messages, serialize_messages
from app.config.settings import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/a2a/recommend-product", tags=["A2A: Recommend Product Agent"])

_logger = get_logger("recommend_product_agent.a2a")


@router.get("/.well-known/agent.json", response_model=AgentCard)
async def agent_card():
    return AgentCard(
        name="recommend_product_agent",
        description="페르소나 특성을 분석해 최적의 뷰티 상품을 추천하는 에이전트",
        url=f"{settings.recommend_agent_url}/a2a/recommend-product",
        skills=[
            AgentSkill(
                id="recommend",
                name="상품 추천",
                description="페르소나 ID 또는 특성 텍스트를 기반으로 상위 상품을 추천합니다",
            )
        ],
    )


@router.post("/tasks/send", response_model=Task)
async def send_task(request: TaskSendRequest, req: Request):
    data = next(
        (p.data for p in request.message.parts if isinstance(p, DataPart)),
        {},
    )

    config = {
        "configurable": {
            "thread_id": request.sessionId or request.id,
            "services": req.app.state.services,
            "user_id": data.get("user_id"),
        },
        "recursion_limit": settings.langgraph_recursion_limit,
    }

    _logger.info("a2a_task_received", task_id=request.id, session_id=request.sessionId)

    try:
        messages = deserialize_messages(data.get("messages", []))
        subgraph_input = {
            "messages": messages,
            "active_persona_id": data.get("active_persona_id"),
        }
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
                    "recommended_products": result.get("recommended_products", []),
                    "active_persona_id": result.get("active_persona_id"),
                    "messages": serialize_messages(result.get("messages", [])),
                    "logs": result.get("logs", []),
                    "status": result.get("status"),
                    "error": result.get("error"),
                },
            }],
        )

    except Exception as e:
        _logger.error("a2a_task_failed", task_id=request.id, error_type=type(e).__name__, exc_info=True)
        return Task(
            id=request.id,
            sessionId=request.sessionId,
            status=TaskStatus.FAILED,
            artifacts=[{"type": "data", "data": {"error": "상품 추천 처리 중 오류가 발생했습니다.", "status": "failed"}}],
        )
