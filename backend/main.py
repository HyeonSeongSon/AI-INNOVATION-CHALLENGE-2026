"""
FastAPI 메인 애플리케이션
CRM Agent API 서버
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import crm_endpoints

# FastAPI 앱 생성
app = FastAPI(
    title="CRM Agent API",
    description="AI 기반 CRM 메시지 생성 API",
    version="1.0.0"
)

# CORS 설정 (프론트엔드와 통신 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 specific origins 사용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(crm_endpoints.router)


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
        port=8001,  # DB 서버(8000)와 충돌 방지
        reload=True  # 개발 환경에서만 사용
    )
