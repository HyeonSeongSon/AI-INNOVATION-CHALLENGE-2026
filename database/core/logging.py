"""
Database API 서버용 자급자족 구조화 로깅 모듈.

backend/app/core/{logging,context,middleware}.py 패턴을 database 서비스 범위에 맞게
최소화하여 복제. database 서비스는 LangGraph를 사용하지 않으므로 request_id만 전파.
"""

import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Dict, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# ============================================================
# request_id contextvar
# ============================================================

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


# ============================================================
# structlog 프로세서
# ============================================================

def _inject_request_id(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    request_id = _request_id_var.get()
    if request_id is not None and "request_id" not in event_dict:
        event_dict["request_id"] = request_id
    return event_dict


# ============================================================
# 설정
# ============================================================

def configure_logging(log_level: str = "INFO") -> None:
    """structlog를 JSON 출력으로 설정. 서버 시작 시 한 번만 호출."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# ============================================================
# HTTP 요청 로깅 미들웨어
# ============================================================

_http_logger = get_logger("http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    모든 요청에 request_id를 부여하고 method/path/status/duration을 JSON으로 기록.
    InternalTokenMiddleware의 401 거절도 포함하려면 가장 마지막에 add_middleware 해야 함.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_id = request.headers.get("X-Request-ID", "")
        request_id = (
            client_id
            if client_id and _REQUEST_ID_RE.match(client_id)
            else generate_request_id()
        )
        set_request_id(request_id)
        request.state.request_id = request_id

        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        _http_logger.info("request_started", method=method, path=path, client=client_host)

        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            _http_logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 1),
            )
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            _http_logger.error(
                "request_failed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 1),
                error_type=type(e).__name__,
            )
            raise
