import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from ..config.settings import settings

_SKIP_PATHS = {"/", "/health", "/ready"}

_UNAUTHORIZED_BODY = json.dumps({"detail": "Unauthorized"}).encode()
_UNAUTHORIZED_HEADERS = [
    (b"content-type", b"application/json"),
    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode()),
]


class InternalTokenMiddleware:
    """X-Internal-Token 헤더 검증 — pure ASGI middleware.

    BaseHTTPMiddleware 대신 pure ASGI로 구현한다:
    BaseHTTPMiddleware 두 개가 중첩되면 anyio receive 채널이 끊겨
    route handler에서 request.body()가 b""을 반환하는 Starlette 버그 회피.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        token = headers.get(b"x-internal-token", b"").decode("latin-1")

        if not settings.internal_token or not hmac.compare_digest(token, settings.internal_token):
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": _UNAUTHORIZED_HEADERS,
            })
            await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})
            return

        await self.app(scope, receive, send)
