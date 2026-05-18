"""
FastAPI 메인 애플리케이션
CRM Agent API 서버
"""

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.api import generated_messages
from app.api import products_pipeline
from app.api import persona_pipeline
from app.api import marketing_api
from app.agents.crm_message_agent.crm_message_agent import CRMMessageAgent
from app.config.settings import settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.core.langsmith_config import configure_langsmith

# Load .env before anything else
load_dotenv(os.path.join(os.path.dirname(__file__), "app/.env"), override=True)

# Configure structured logging (must be first)
configure_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=True,
    environment=os.getenv("ENVIRONMENT", "production"),
)

logger = get_logger("main")

# Configure LangSmith tracing
configure_langsmith()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with AsyncConnectionPool(
        conninfo=settings.postgres_url,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    ) as pool:
        await pool.wait()  # 최소 1개 연결이 실제로 맺어질 때까지 대기
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        app.state.pool = pool
        app.state.agent_v2 = CRMMessageAgent(checkpointer=checkpointer)
        logger.info("postgres_checkpointer_ready")
        yield


# FastAPI 앱 생성
app = FastAPI(
    title="CRM Agent API",
    description="AI 기반 CRM 메시지 생성 API",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware (order matters: outermost first)
app.add_middleware(RequestLoggingMiddleware)
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(generated_messages.router)
app.include_router(products_pipeline.router)
app.include_router(persona_pipeline.router)
app.include_router(marketing_api.router)


@app.get("/")
def read_root():
    """헬스 체크"""
    return {
        "status": "ok",
        "message": "CRM Agent API is running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check(req: Request):
    """상세 헬스 체크"""
    agent_ok = getattr(req.app.state, "agent_v2", None) is not None

    db_ok = False
    pool = getattr(req.app.state, "pool", None)
    if pool is not None:
        try:
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False

    overall = "healthy" if (agent_ok and db_ok) else "degraded"
    return {
        "status": overall,
        "services": {
            "agent": "ok" if agent_ok else "not_initialized",
            "database": "ok" if db_ok else "unavailable",
        },
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8005")),
    )
