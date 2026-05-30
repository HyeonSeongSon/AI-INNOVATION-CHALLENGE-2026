"""
Database API Server
DB CRUD + Pipeline API (port 8020)
"""

import hmac
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
