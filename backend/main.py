"""
FastAPI 메인 애플리케이션
CRM Agent API 서버
"""

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.api import marketing_api
from app.api import generated_messages
from app.agents.supervisor.marketing_agent import MarketingAgent
from app.agents.marketing_assistant.marketing_assistant_agent import MarketingAgent as MarketingAssistantAgent
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
    postgres_url = os.getenv("POSTGRES_URL")
    async with AsyncConnectionPool(
        conninfo=postgres_url,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    ) as pool:
        await pool.wait()  # 최소 1개 연결이 실제로 맺어질 때까지 대기
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        app.state.agent = MarketingAgent(checkpointer=checkpointer)
        app.state.agent_v2 = MarketingAssistantAgent(checkpointer=checkpointer)
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 specific origins 사용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(marketing_api.router)
app.include_router(generated_messages.router)


@app.get("/")
def read_root():
    """헬스 체크"""
    return {
        "status": "ok",
        "message": "CRM Agent API is running",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    """상세 헬스 체크"""
    return {
        "status": "healthy",
        "services": {
            "api": "ok",
            "agent": "ok"
        }
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8005,
        workers=2
    )
