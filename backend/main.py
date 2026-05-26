"""
FastAPI API Gateway (port 8005)
Auth + BFF proxy — 외부 노출 서버.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_router
from app.api import db_proxy
from app.api import crm_proxy
from app.config.settings import settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.core.auth import get_auth_provider
from app.core.cleanup import cleanup_loop

# Load .env before anything else
load_dotenv(os.path.join(os.path.dirname(__file__), "app/.env"), override=True)

# Configure structured logging (must be first)
configure_logging(
    log_level=settings.log_level,
    json_output=True,
    environment=settings.environment,
)

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    from app.core.rate_limiter import PostgresRateLimiter
    from app.core.database import SessionLocal
    app.state.auth_provider = get_auth_provider()
    _auth_log = logger.warning if settings.auth_mode == "api_key" else logger.info
    _auth_log("auth_mode_active", auth_mode=settings.auth_mode)

    app.state.login_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_login_max_requests,
        window_seconds=settings.rate_limit_login_window_seconds,
    )
    app.state.register_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_register_max_requests,
        window_seconds=settings.rate_limit_register_window_seconds,
    )
    app.state.lockout_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.lockout_per_ip_max_attempts,
        window_seconds=settings.lockout_per_ip_window_seconds,
    )

    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("cleanup_worker_started", interval_seconds=settings.cleanup_interval_seconds)
    logger.info("api_gateway_initialized")

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("cleanup_worker_stopped")
    await db_proxy.close_internal_client()
    await crm_proxy.close_crm_client()


app = FastAPI(
    title="API Gateway",
    description="Auth + BFF Proxy",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
_allowed_origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(db_proxy.router)
app.include_router(crm_proxy.router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Gateway is running", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "port": 8005}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
    )
