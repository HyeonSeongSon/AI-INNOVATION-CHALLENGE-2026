"""
FastAPI 메인 애플리케이션
CRM Agent API 서버
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import marketing_api
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.core.langsmith_config import configure_langsmith

# Load .env before anything else
load_dotenv(os.path.join(os.path.dirname(__file__), "app/.env"))

# Configure structured logging (must be first)
configure_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=True,
    environment=os.getenv("ENVIRONMENT", "production"),
)

logger = get_logger("main")

# Configure LangSmith tracing
configure_langsmith()

# FastAPI 앱 생성
app = FastAPI(
    title="CRM Agent API",
    description="AI 기반 CRM 메시지 생성 API",
    version="1.0.0"
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


@app.on_event("startup")
async def startup_event():
    logger.info(
        "application_started",
        port=8005,
        environment=os.getenv("ENVIRONMENT", "production"),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8005,
        reload=True  # 개발 환경에서만 사용
    )
