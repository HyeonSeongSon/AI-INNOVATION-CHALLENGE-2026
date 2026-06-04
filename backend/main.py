"""
FastAPI API Gateway (port 8005)
Auth + BFF proxy — 외부 노출 서버.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_router
from app.api import db_proxy
from app.api import crm_proxy
from app.config.settings import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.core.body_limit import BodySizeLimitMiddleware, PayloadTooLargeError
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


def _seed_admin_if_needed() -> None:
    email = settings.admin_seed_email.strip()
    password = settings.admin_seed_password
    if not email or not password:
        return

    from app.core.database import SessionLocal
    from app.core.models import User
    from app.core.security import hash_password

    with SessionLocal() as db:
        if db.query(User).filter(User.email == email).first():
            logger.info("admin_seed_skipped", reason="already_exists")
            return
        db.add(User(email=email, password_hash=hash_password(password), role="admin"))
        db.commit()

    logger.info("admin_seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.rate_limiter import PostgresRateLimiter
    from app.core.database import SessionLocal
    _seed_admin_if_needed()
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
    app.state.chat_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_chat_max_requests,
        window_seconds=settings.rate_limit_chat_window_seconds,
    )
    app.state.refresh_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_refresh_max_requests,
        window_seconds=settings.rate_limit_refresh_window_seconds,
    )
    app.state.logout_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_logout_max_requests,
        window_seconds=settings.rate_limit_logout_window_seconds,
    )
    app.state.persona_text_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_persona_text_max_requests,
        window_seconds=settings.rate_limit_persona_text_window_seconds,
    )
    app.state.persona_upload_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_persona_upload_max_requests,
        window_seconds=settings.rate_limit_persona_upload_window_seconds,
    )
    app.state.conversation_write_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_conversation_write_max_requests,
        window_seconds=settings.rate_limit_conversation_write_window_seconds,
    )
    app.state.persona_delete_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_persona_delete_max_requests,
        window_seconds=settings.rate_limit_persona_delete_window_seconds,
    )
    app.state.product_upload_limiter = PostgresRateLimiter(
        session_factory=SessionLocal,
        max_requests=settings.rate_limit_product_upload_max_requests,
        window_seconds=settings.rate_limit_product_upload_window_seconds,
    )

    # max_workers=20: DB 커넥션풀(pool_size=10, max_overflow=20)보다 작게 설정해 풀 고갈 방지
    db_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="db_worker")
    app.state.db_executor = db_executor

    app.state.crm_client = httpx.AsyncClient(
        base_url=settings.crm_service_url,
        headers={"X-Internal-Token": settings.internal_token},
        timeout=httpx.Timeout(settings.http_timeout_long),
    )
    app.state.internal_client = httpx.AsyncClient(
        base_url=settings.database_api_url,
        headers={"X-Internal-Token": settings.internal_token},
        timeout=httpx.Timeout(settings.http_timeout_long),
    )

    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("cleanup_worker_started", interval_seconds=settings.cleanup_interval_seconds)
    logger.info("api_gateway_initialized")

    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("cleanup_worker_stopped")
        await app.state.crm_client.aclose()
        await app.state.internal_client.aclose()
        db_executor.shutdown(wait=False)


app = FastAPI(
    title="API Gateway",
    description="Auth + BFF Proxy",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(PayloadTooLargeError)
async def payload_too_large_handler(request: Request, exc: PayloadTooLargeError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=413, content={"detail": "요청 바디가 너무 큽니다."})


app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_chat_body_bytes)
app.add_middleware(RequestLoggingMiddleware)
_allowed_origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Cache-Control"],
    max_age=3600,
)

app.include_router(auth_router.router)
app.include_router(db_proxy.router)
app.include_router(crm_proxy.router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Gateway is running", "version": "1.0.0"}


@app.get("/health")
async def health_check(req: Request):
    from app.core.database import check_connection

    db_ok = await asyncio.to_thread(check_connection)
    crm_ok = getattr(req.app.state, "crm_client", None) is not None
    internal_ok = getattr(req.app.state, "internal_client", None) is not None

    overall = "healthy" if (db_ok and crm_ok and internal_ok) else "degraded"
    return {
        "status": overall,
        "port": 8005,
        "services": {
            "database": "ok" if db_ok else "unavailable",
            "crm_client": "ok" if crm_ok else "not_initialized",
            "internal_client": "ok" if internal_ok else "not_initialized",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
    )
