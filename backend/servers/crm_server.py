"""
CRM Service — LangGraph 오케스트레이터 + Pipeline SSE (port 8006)
프론트엔드가 직접 호출하는 에이전트 채팅 및 데이터 등록 파이프라인 서버.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../app/.env"))

from fastapi import FastAPI, Request
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.agents.crm_message_agent.crm_message_agent import CRMMessageAgent
from app.api import marketing_api, products_pipeline, persona_pipeline
from app.api import db_proxy
from app.api.upload_jobs import cleanup_expired_jobs
from app.config.settings import settings
from app.core.data_loader import validate_static_configs
from app.core.internal_auth import InternalTokenMiddleware
from app.core.logging import configure_logging, get_logger
from app.core.langsmith_config import configure_langsmith
from app.core.middleware import RequestLoggingMiddleware
from app.core.http_client_registry import close_all

configure_logging(
    log_level=settings.log_level,
    json_output=True,
    environment=settings.environment,
)

logger = get_logger("crm_server")

configure_langsmith()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.agents.shared.persona.persona_client import PersonaClient
    from app.agents.data_registration_agent.services.product_registration import ProductRegistrationService

    app.state.persona_client = PersonaClient()
    app.state.registration = ProductRegistrationService()

    validate_static_configs()

    async with AsyncConnectionPool(
        conninfo=settings.postgres_url,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    ) as pool:
        await pool.wait()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        app.state.pool = pool
        app.state.agent_v2 = CRMMessageAgent(checkpointer=checkpointer)
        logger.info("crm_services_initialized")

        async def _upload_cleanup_loop() -> None:
            while True:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                try:
                    removed = await cleanup_expired_jobs(settings.upload_job_ttl_seconds)
                    if removed:
                        logger.info("upload_jobs_cleaned", removed=removed)
                except Exception:
                    logger.error("upload_cleanup_failed", exc_info=True)

        upload_cleanup_task = asyncio.create_task(_upload_cleanup_loop())
        logger.info("upload_cleanup_worker_started")

        yield

        upload_cleanup_task.cancel()
        try:
            await upload_cleanup_task
        except asyncio.CancelledError:
            pass
        await close_all()
        await db_proxy.close_internal_client()


app = FastAPI(
    title="CRM Service",
    description="LangGraph CRM 오케스트레이터 + 데이터 등록 파이프라인",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(InternalTokenMiddleware)

app.include_router(marketing_api.router)
app.include_router(products_pipeline.router)
app.include_router(persona_pipeline.router)


@app.get("/health")
async def health(req: Request):
    agent_ok = getattr(req.app.state, "agent_v2", None) is not None
    pool = getattr(req.app.state, "pool", None)
    db_ok = False
    if pool is not None:
        try:
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
            db_ok = True
        except Exception as e:
            logger.warning("health_check_db_failed", error=str(e))

    overall = "healthy" if (agent_ok and db_ok) else "degraded"
    return {
        "status": overall,
        "services": {
            "agent": "ok" if agent_ok else "not_initialized",
            "database": "ok" if db_ok else "unavailable",
        },
    }


@app.get("/ready")
async def ready(req: Request):
    agent_ok = getattr(req.app.state, "agent_v2", None) is not None
    if not agent_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Agent not ready")
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servers.crm_server:app", host="0.0.0.0", port=8006, reload=True)
