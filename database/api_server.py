"""
AI Innovation Challenge 2026 - API Server
FastAPI 기반 RESTful API
새로운 테이블 스키마 (table_type.md 기준)
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models import Persona, Product, AnalysisResult, SearchQuery
from api_endpoints import router as db_router

app = FastAPI(
    title="AI Innovation Challenge 2026 API",
    description="화장품 추천 시스템 API",
    version="2.0.0"
)

# 라우터 등록
app.include_router(db_router)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Pydantic Models (Request/Response)
# ============================================================

class PersonaResponse(BaseModel):
    """페르소나 응답 모델"""
    model_config = ConfigDict(from_attributes=True)

    persona_id: str
    name: str
    gender: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    skin_type: List[str] = Field(default=[])
    skin_concerns: List[str] = Field(default=[])
    personal_color: Optional[str] = None
    preferred_colors: List[str] = Field(default=[])
    preferred_ingredients: List[str] = Field(default=[])
    avoided_ingredients: List[str] = Field(default=[])


class ProductResponse(BaseModel):
    """상품 응답 모델"""
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    product_name: str
    brand: Optional[str] = None
    product_tag: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = 0
    original_price: Optional[int] = None
    discount_rate: Optional[int] = None
    sale_price: Optional[int] = None
    skin_type: List[str] = Field(default=[])
    skin_concerns: List[str] = Field(default=[])
    preferred_colors: List[str] = Field(default=[])
    preferred_ingredients: List[str] = Field(default=[])
    product_image_url: List[str] = Field(default=[])
    product_page_url: Optional[str] = None


class AnalysisResultResponse(BaseModel):
    """분석 결과 응답 모델"""
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    persona_id: str
    analysis_result: Optional[str] = None


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
def root():
    """API 루트"""
    return {
        "message": "AI Innovation Challenge 2026 API",
        "version": "2.0.0",
        "schema": "table_type.md v1.0",
        "endpoints": {
            "products": "/api/products",
            "personas": "/api/personas",
            "analysis_results": "/api/analysis-results",
            "search_queries": "/api/search-queries",
            "health": "/api/health"
        }
    }


# ============================================================
# Products API
# ============================================================

@app.get("/api/products", tags=["Products"])
def get_products(
    limit: int = 20,
    offset: int = 0,
    brand: Optional[str] = None,
    product_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    상품 목록 조회
    - brand: 브랜드명으로 필터링
    - product_name: 상품명으로 검색 (부분 일치)
    """
    query = db.query(Product)

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if product_name:
        query = query.filter(Product.product_name.ilike(f"%{product_name}%"))

    total = query.count()
    products = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters": {
            "brand": brand,
            "product_name": product_name
        },
        "products": [
            {
                "product_id": p.product_id,
                "product_name": p.product_name,
                "brand": p.brand,
                "product_tag": p.product_tag,
                "sale_price": p.sale_price,
                "rating": float(p.rating) if p.rating else None,
                "review_count": p.review_count or 0,
                "product_image_url": p.product_image_url[:3] if p.product_image_url else []
            }
            for p in products
        ]
    }


@app.get("/api/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def get_product(product_id: str, db: Session = Depends(get_db)):
    """특정 상품 상세 조회"""
    product = db.query(Product).filter(Product.product_id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


# ============================================================
# Personas API
# ============================================================

@app.get("/api/personas", tags=["Personas"])
def get_personas(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """모든 페르소나 조회"""
    query = db.query(Persona)
    total = query.count()
    personas = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "personas": [
            {
                "persona_id": p.persona_id,
                "name": p.name,
                "gender": p.gender,
                "age": p.age,
                "skin_type": p.skin_type,
                "skin_concerns": p.skin_concerns,
                "persona_created_at": p.persona_created_at.isoformat() if p.persona_created_at else None
            }
            for p in personas
        ]
    }


@app.get("/api/personas/{persona_id}", response_model=PersonaResponse, tags=["Personas"])
def get_persona(persona_id: str, db: Session = Depends(get_db)):
    """특정 페르소나 조회"""
    persona = db.query(Persona).filter(Persona.persona_id == persona_id).first()

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    return persona


# ============================================================
# Analysis Results API
# ============================================================

@app.get("/api/analysis-results", tags=["Analysis"])
def get_analysis_results(
    persona_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """분석 결과 목록 조회"""
    query = db.query(AnalysisResult)

    if persona_id:
        query = query.filter(AnalysisResult.persona_id == persona_id)

    total = query.count()
    results = query.order_by(AnalysisResult.analysis_created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters": {
            "persona_id": persona_id
        },
        "results": [
            {
                "analysis_id": r.analysis_id,
                "persona_id": r.persona_id,
                "analysis_result": r.analysis_result,
                "analysis_created_at": r.analysis_created_at.isoformat() if r.analysis_created_at else None
            }
            for r in results
        ]
    }


@app.get("/api/analysis-results/{analysis_id}", response_model=AnalysisResultResponse, tags=["Analysis"])
def get_analysis_result(analysis_id: int, db: Session = Depends(get_db)):
    """특정 분석 결과 조회"""
    result = db.query(AnalysisResult).filter(AnalysisResult.analysis_id == analysis_id).first()

    if not result:
        raise HTTPException(status_code=404, detail="Analysis result not found")

    return result


# ============================================================
# Search Queries API
# ============================================================

@app.get("/api/search-queries", tags=["Search"])
def get_search_queries(
    analysis_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """검색 쿼리 목록 조회"""
    query = db.query(SearchQuery)

    if analysis_id:
        query = query.filter(SearchQuery.analysis_id == analysis_id)

    total = query.count()
    queries = query.order_by(SearchQuery.query_created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters": {
            "analysis_id": analysis_id
        },
        "queries": [
            {
                "query_id": q.query_id,
                "analysis_id": q.analysis_id,
                "search_query": q.search_query,
                "query_created_at": q.query_created_at.isoformat() if q.query_created_at else None
            }
            for q in queries
        ]
    }


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
