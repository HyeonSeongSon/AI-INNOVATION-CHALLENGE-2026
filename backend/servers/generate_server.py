import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../app/.env"))

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.agents.generate_message_agent.a2a_agent import router
from app.agents.generate_message_agent.workflow import build_workflow
from app.core.body_limit import BodySizeLimitMiddleware, PayloadTooLargeError
from app.core.internal_auth import InternalTokenMiddleware
from app.core.middleware import RequestLoggingMiddleware
from app.core.logging import configure_logging, get_logger
from app.core.http_client_registry import close_all
from app.config.settings import settings

configure_logging(
    log_level=settings.log_level,
    json_output=True,
    environment=settings.environment,
)

_logger = get_logger("generate_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.containers import GenerateMessageServices
    from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator
    from app.agents.generate_message_agent.services.quality_check import QualityChecker
    from app.agents.generate_message_agent.services.apply_feedback import ApplyFeedback

    app.state.services = GenerateMessageServices(
        generator=CrmMessageGenerator(),
        checker=QualityChecker(),
        applier=ApplyFeedback(),
    )
    app.state.graph = build_workflow()
    _logger.info("services_and_graph_initialized")
    yield
    await close_all()


app = FastAPI(title="Generate Message Agent", version="1.0.0", lifespan=lifespan)


@app.exception_handler(PayloadTooLargeError)
async def payload_too_large_handler(request: Request, exc: PayloadTooLargeError):
    return JSONResponse(status_code=413, content={"detail": "요청 본문이 너무 큽니다."})


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(InternalTokenMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_chat_body_bytes)
app.include_router(router)


@app.get("/health")
def health(req: Request):
    graph_ok = getattr(req.app.state, "graph", None) is not None
    return {
        "status": "ok" if graph_ok else "degraded",
        "agent": "generate_message_agent",
        "graph": "ok" if graph_ok else "not_initialized",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servers.generate_server:app", host="0.0.0.0", port=8002, reload=True)
