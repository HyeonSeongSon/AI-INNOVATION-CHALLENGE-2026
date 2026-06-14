"""
요청/응답 로깅 및 상관관계 ID를 위한 FastAPI 미들웨어.

모든 수신 요청에 고유한 request_id가 부여되며,
contextvars를 통해 전체 에이전트 실행 과정에 전파됩니다.
"""

import re
import time

from starlette.types import ASGIApp, Receive, Scope, Send

from .context import generate_request_id, set_request_id
from .logging import get_logger

# 영숫자 + 하이픈만 허용, 최대 64자. 클라이언트 제공 X-Request-ID 검증용
_REQUEST_ID_RE = re.compile(r'^[a-zA-Z0-9\-]{1,64}$')

logger = get_logger("http")


class RequestLoggingMiddleware:
    """요청/응답 로깅 — pure ASGI middleware.

    BaseHTTPMiddleware 대신 pure ASGI로 구현한다:
    BaseHTTPMiddleware.call_next()는 anyio task group + memory channel을 생성해
    receive를 전달하는데, 중첩 시 body stream이 끊기는 Starlette 버그 회피.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # request_id 생성
        headers = dict(scope.get("headers", []))
        client_request_id = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = (
            client_request_id
            if client_request_id and _REQUEST_ID_RE.match(client_request_id)
            else generate_request_id()
        )
        set_request_id(request_id)

        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_host = client[0] if client else "unknown"

        logger.info(
            "request_started",
            method=method,
            path=path,
            client=client_host,
        )

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # X-Request-ID 응답 헤더 추가
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers_list}
            await send(message)

        failed = False
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            failed = True
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 1),
                error_type=type(e).__name__,
            )
            raise

        if not failed:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 1),
            )
