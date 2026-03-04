"""
AI Innovation Challenge 2026 - API Server
FastAPI 기반 RESTful API
새로운 테이블 스키마 (table_type.md 기준)
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models import Persona, Product, AnalysisResult, SearchQuery
from api_endpoints import router as db_router
from pipeline_router import router as pipeline_router

app = FastAPI(
    title="AI Innovation Challenge 2026 API",
    description="화장품 추천 시스템 API",
    version="2.0.0"
)

# 라우터 등록
app.include_router(db_router)
app.include_router(pipeline_router)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health Check
# ============================================================

@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """헬스 체크"""
    try:
        # 데이터베이스 연결 확인
        db.execute(text("SELECT 1"))

        # 테이블 카운트
        product_count = db.query(Product).count()
        persona_count = db.query(Persona).count()
        analysis_count = db.query(AnalysisResult).count()
        search_count = db.query(SearchQuery).count()

        return {
            "status": "healthy",
            "database": "connected",
            "schema_version": "2.0",
            "tables": {
                "products": product_count,
                "personas": persona_count,
                "analysis_results": analysis_count,
                "search_queries": search_count
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
