"""
PostgreSQL 데이터베이스 API 엔드포인트
새로운 테이블 스키마에 맞춰 재구성 (POST 전용)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db

# 라우터 생성
router = APIRouter(prefix="/api", tags=["Database"])


# ============================================================
# Pydantic Models
# ============================================================

class PersonaCreate(BaseModel):
    """페르소나 생성 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])
    name: str = Field(..., description="이름", examples=["김지현"])
    gender: Optional[str] = Field(None, description="성별", examples=["여성"])
    age: Optional[int] = Field(None, description="나이", examples=[28])
    occupation: Optional[str] = Field(None, description="직업", examples=["마케터"])
    skin_type: Optional[List[str]] = Field(default=[], description="피부 타입", examples=[["지성", "복합성"]])
    skin_concerns: Optional[List[str]] = Field(default=[], description="피부 고민", examples=[["모공", "칙칙함"]])
    personal_color: Optional[str] = Field(None, description="퍼스널 컬러", examples=["웜톤"])
    shade_number: Optional[int] = Field(None, description="셰이드 번호", examples=[21])
    preferred_colors: Optional[List[str]] = Field(default=[], description="선호 색상", examples=[["코랄", "핑크"]])
    preferred_ingredients: Optional[List[str]] = Field(default=[], description="선호 성분", examples=[["히알루론산", "나이아신아마이드"]])
    avoided_ingredients: Optional[List[str]] = Field(default=[], description="기피 성분", examples=[["알코올", "파라벤"]])
    preferred_scents: Optional[List[str]] = Field(default=[], description="선호 향", examples=["플로럴"])
    values: Optional[List[str]] = Field(default=[], description="가치관", examples=[["비건", "친환경"]])
    skincare_routine: Optional[str] = Field(None, description="스킨케어 루틴", examples=["간단한 루틴"])
    main_environment: Optional[str] = Field(None, description="주 활동 환경", examples=["실내"])
    preferred_texture: Optional[List[str]] = Field(default=[], description="선호 제형", examples=[["에센스", "세럼"]])
    pets: Optional[str] = Field(None, description="반려동물 유무", examples=["없음"])
    avg_sleep_hours: Optional[int] = Field(None, description="평균 수면 시간", examples=[6])
    stress_level: Optional[str] = Field(None, description="스트레스 수준", examples=["높음"])
    digital_device_usage_time: Optional[int] = Field(None, description="디지털 기기 사용 시간", examples=[8])
    shopping_style: Optional[str] = Field(None, description="쇼핑 스타일", examples=["신중형"])
    purchase_decision_factors: Optional[List[str]] = Field(default=[], description="구매 결정 요인", examples=[["리뷰", "성분"]])


class AnalysisResultCreate(BaseModel):
    """분석 결과 생성 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])
    analysis_result: str = Field(..., description="분석 결과 텍스트", examples=["지성 피부에 적합한 모공 케어 제품 추천"])


class SearchQueryCreate(BaseModel):
    """검색 쿼리 생성 요청"""
    analysis_id: int = Field(..., description="분석 ID", examples=[1])
    search_query: str = Field(..., description="검색 쿼리", examples=["지성 피부 모공 케어 세럼"])


class ProductCreate(BaseModel):
    """상품 생성 요청"""
    product_id: str = Field(..., description="상품 ID", examples=["A20251200001"])
    vectordb_id: Optional[str] = Field(None, description="VectorDB ID")
    product_name: str = Field(..., description="상품명", examples=["수분 세럼 50ml"])
    brand: Optional[str] = Field(None, description="브랜드", examples=["설화수"])
    product_tag: Optional[str] = Field(None, description="상품 태그", examples=["에센스&세럼&오일"])
    rating: Optional[float] = Field(None, description="별점", examples=[4.5])
    review_count: Optional[int] = Field(0, description="리뷰 수", examples=[128])
    original_price: Optional[int] = Field(None, description="원가", examples=[50000])
    discount_rate: Optional[int] = Field(None, description="할인율", examples=[20])
    sale_price: Optional[int] = Field(None, description="판매가", examples=[40000])
    skin_type: Optional[List[str]] = Field(default=[], description="피부 타입")
    skin_concerns: Optional[List[str]] = Field(default=[], description="피부 고민")
    preferred_colors: Optional[List[str]] = Field(default=[], description="선호 색상")
    preferred_ingredients: Optional[List[str]] = Field(default=[], description="선호 성분")
    avoided_ingredients: Optional[List[str]] = Field(default=[], description="기피 성분")
    preferred_scents: Optional[List[str]] = Field(default=[], description="선호 향")
    values: Optional[List[str]] = Field(default=[], description="가치관")
    exclusive_product: Optional[str] = Field(None, description="전용 제품")
    personal_color: Optional[List[str]] = Field(default=[], description="퍼스널 컬러")
    skin_shades: Optional[List[int]] = Field(default=[], description="피부톤 번호")
    product_image_url: Optional[List[str]] = Field(default=[], description="상품 이미지 URL")
    product_page_url: Optional[str] = Field(None, description="상품 페이지 URL")


# ============================================================
# Response Models
# ============================================================

class PersonaResponse(BaseModel):
    """페르소나 응답"""
    persona_id: str
    name: str
    created_at: Optional[datetime] = None


class AnalysisResultResponse(BaseModel):
    """분석 결과 응답"""
    analysis_id: int
    persona_id: str
    analysis_created_at: Optional[datetime] = None


class SearchQueryResponse(BaseModel):
    """검색 쿼리 응답"""
    query_id: int
    analysis_id: int
    search_query: str
    query_created_at: Optional[datetime] = None


class ProductResponse(BaseModel):
    """상품 응답"""
    product_id: str
    product_name: str
    brand: Optional[str] = None
    sale_price: Optional[int] = None
    rating: Optional[float] = None
    product_created_at: Optional[datetime] = None


# ============================================================
# API Endpoints - POST Only
# ============================================================

@router.post("/personas", response_model=PersonaResponse, summary="페르소나 생성")
async def create_persona(request: PersonaCreate, db: Session = Depends(get_db)):
    """
    새로운 페르소나 생성

    **테이블:** personas

    **필수 필드:**
    - persona_id: 고유 ID
    - name: 이름
    """
    from models import Persona

    # 중복 확인
    existing = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Persona with ID '{request.persona_id}' already exists")

    # 새 페르소나 생성
    persona = Persona(**request.dict())
    db.add(persona)
    db.commit()
    db.refresh(persona)

    return PersonaResponse(
        persona_id=persona.persona_id,
        name=persona.name,
        created_at=persona.persona_created_at
    )


@router.post("/analysis-results", response_model=AnalysisResultResponse, summary="분석 결과 생성")
async def create_analysis_result(request: AnalysisResultCreate, db: Session = Depends(get_db)):
    """
    페르소나 분석 결과 생성

    **테이블:** analysis_results

    **필수 필드:**
    - persona_id: 페르소나 ID (FK)
    - analysis_result: 분석 결과 텍스트
    """
    from models import AnalysisResult, Persona

    # 페르소나 존재 확인
    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

    # 분석 결과 생성
    analysis = AnalysisResult(**request.dict())
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return AnalysisResultResponse(
        analysis_id=analysis.analysis_id,
        persona_id=analysis.persona_id,
        analysis_created_at=analysis.analysis_created_at
    )


@router.post("/search-queries", response_model=SearchQueryResponse, summary="검색 쿼리 생성")
async def create_search_query(request: SearchQueryCreate, db: Session = Depends(get_db)):
    """
    검색 쿼리 생성

    **테이블:** search_queries

    **필수 필드:**
    - analysis_id: 분석 ID (FK)
    - search_query: 검색 쿼리 텍스트
    """
    from models import SearchQuery, AnalysisResult

    # 분석 결과 존재 확인
    analysis = db.query(AnalysisResult).filter(AnalysisResult.analysis_id == request.analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis with ID '{request.analysis_id}' not found")

    # 검색 쿼리 생성
    search = SearchQuery(**request.dict())
    db.add(search)
    db.commit()
    db.refresh(search)

    return SearchQueryResponse(
        query_id=search.query_id,
        analysis_id=search.analysis_id,
        search_query=search.search_query,
        query_created_at=search.query_created_at
    )


@router.post("/products", response_model=ProductResponse, summary="상품 생성")
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    """
    단일 상품 생성

    **테이블:** products

    **필수 필드:**
    - product_id: 상품 ID
    - product_name: 상품명
    """
    from models import Product

    # 중복 확인
    existing = db.query(Product).filter(Product.product_id == request.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product with ID '{request.product_id}' already exists")

    # 새 상품 생성
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    db.refresh(product)

    return ProductResponse(
        product_id=product.product_id,
        product_name=product.product_name,
        brand=product.brand,
        sale_price=product.sale_price,
        rating=float(product.rating) if product.rating else None,
        product_created_at=product.product_created_at
    )


# ============================================================
# 헬스 체크
# ============================================================

@router.get("/health", summary="API 헬스 체크")
async def health_check():
    """
    API 서버 상태 확인
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "database": "postgresql",
        "schema_version": "1.0"
    }


# ============================================================
# API 서버에 라우터 추가하는 방법
# ============================================================

"""
main API 서버 파일에 다음 코드 추가:

from database.api_endpoints import router as db_router
app.include_router(db_router)
"""
