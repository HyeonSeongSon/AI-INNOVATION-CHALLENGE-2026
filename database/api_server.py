"""
Database API Server
DB CRUD + Pipeline API (port 8020)
"""

import hmac
import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

load_dotenv()

from routers.api_endpoints import router as db_router
from routers.conversations_router import router as conversations_router
from routers.generated_messages_router import router as generated_messages_router

_INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")

if not _INTERNAL_TOKEN:
    raise RuntimeError(
        "INTERNAL_TOKEN 환경변수가 설정되지 않았습니다. "
        "'openssl rand -hex 32'로 생성 후 .env에 추가하세요."
    )
if len(_INTERNAL_TOKEN) < 32:
    raise RuntimeError("INTERNAL_TOKEN은 최소 32자 이상이어야 합니다.")

_SKIP_PATHS = {"/", "/health"}
_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10MB


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = _MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except ValueError:
                content_length = 0
            if content_length > self.max_body_bytes:
                await self._send_413(send)
                return

        total_bytes = 0

        async def limited_receive() -> dict:
            nonlocal total_bytes
            message = await receive()
            if message.get("type") == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_body_bytes:
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLargeError:
            await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        body = json.dumps({"detail": "요청 바디가 너무 큽니다."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class _PayloadTooLargeError(Exception):
    pass


class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)
        token = request.headers.get("X-Internal-Token", "")
        if not token or not hmac.compare_digest(token, _INTERNAL_TOKEN):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


app = FastAPI(
    title="Database API",
    description="DB CRUD 및 Pipeline API",
    version="1.0.0",
)

# InternalTokenMiddleware는 CORS보다 먼저 등록 (인증 먼저 체크)
app.add_middleware(InternalTokenMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=_MAX_BODY_BYTES)

_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(db_router)
app.include_router(conversations_router)
app.include_router(generated_messages_router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Database API is running", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "port": 8020}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8020, reload=True)
