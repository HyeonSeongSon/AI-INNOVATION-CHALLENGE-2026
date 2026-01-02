"""
FastAPI 메인 애플리케이션
CRM Agent + 페르소나 파이프라인 + DB API 통합
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ✅ [핵심] 모든 라우터 모듈 임포트
# (파일이 존재해도 여기서 임포트하고 등록하지 않으면 작동하지 않습니다)
from app.api import persona_pipeline      # 페르소나 생성/분석/삭제/조회
from app.api import crm_agent_api         # CRM 메시지 생성
from database import api_endpoints as db_api  # 상품/브랜드 조회

# DB 초기화 함수
from database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 실행될 로직
    try:
        init_db()
        print("✅ 데이터베이스 연결 및 초기화 완료")
    except Exception as e:
        print(f"⚠️ DB 초기화 중 경고: {e}")
    yield

app = FastAPI(
    title="AI Innovation Challenge API",
    description="통합 API 서버 (Persona, CRM, DB)",
    version="2.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🔗 라우터 등록 (모든 기능을 여기에 연결합니다!)
# ============================================================

# 1. 페르소나 파이프라인
# (내부 prefix='/pipeline' + 외부 prefix='/api' => /api/pipeline/...)
app.include_router(persona_pipeline.router, prefix="/api")

# 2. 데이터베이스 API
# (내부 prefix='' + 외부 prefix='/api' => /api/products 등)
app.include_router(db_api.router, prefix="/api")

# 3. CRM 에이전트 API
# (crm_agent_api.py 내부에 이미 prefix='/api/crm'이 설정되어 있으므로, 
#  여기서는 prefix를 따로 붙이지 않습니다. 그래야 /api/crm/generate 가 됩니다.)
app.include_router(crm_agent_api.router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Unified Backend Server Running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # 도커 컨테이너 내부 포트 8005번으로 실행
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)