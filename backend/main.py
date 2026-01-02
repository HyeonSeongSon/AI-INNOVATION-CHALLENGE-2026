"""
FastAPI 메인 애플리케이션
CRM Agent API 서버 + 페르소나 파이프라인 + DB API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# [1] 라우터 모듈 임포트
from app.api import crm_agent_api
from app.api import persona_pipeline
from database import api_endpoints as db_api  # ✅ DB API 임포트 필수

# FastAPI 앱 생성
app = FastAPI(
    title="CRM Agent & Persona API",
    description="AI 기반 CRM 메시지 생성 및 페르소나 분석 API",
    version="2.0.0"
)

# CORS 설정 (프론트엔드 통신 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 보안상 프로덕션에서는 도메인 지정 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [2] 라우터 등록 (URL 경로 연결)
# ⚠️ [핵심 수정] prefix="/api"를 추가하여 프론트엔드 요청(/api/...)과 매칭시킵니다.
app.include_router(crm_agent_api.router, prefix="/api")
app.include_router(persona_pipeline.router, prefix="/api")
app.include_router(db_api.router, prefix="/api")

@app.get("/")
def read_root():
    """서버 상태 확인"""
    return {
        "status": "ok",
        "message": "Backend Server Running (Port: 8005 -> Docker: 8050)",
        "version": "2.0.0"
    }

@app.get("/health")
def health_check():
    """상세 헬스 체크"""
    return {
        "status": "healthy",
        "services": {
            "api": "ok",
            "agent": "ok",
            "persona_pipeline": "active",
            "database": "connected"
        }
    }

if __name__ == "__main__":
    import uvicorn
    # ⚠️ 중요: 도커 내부에서는 8005번으로 실행해야 합니다.
    # (docker-compose.yml에서 8050:8005로 설정했기 때문)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8005,
        reload=True
    )