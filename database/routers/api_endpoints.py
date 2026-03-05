"""
PostgreSQL 데이터베이스 API 엔드포인트
새로운 테이블 스키마에 맞춰 재구성 (POST 전용)
"""

import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from core.database import get_db

# 라우터 생성
router = APIRouter(prefix="/api", tags=["Database"])


def _build_ai_analysis(persona_summary: str | None) -> dict | None:
    """persona_summary 텍스트로부터 ai_analysis 딕셔너리를 구성한다."""
    if not persona_summary:
        return None
    keywords = ["건성", "지성", "복합성", "민감성", "중성", "아토피"]
    primary = "맞춤형 뷰티"
    for kw in keywords:
        if kw in persona_summary:
            primary = f"{kw} 피부"
            break
    return {"primary_category": primary, "ai_analysis_text": persona_summary}


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
    persona_summary: Optional[str] = Field(None, description="AI 생성 페르소나 요약")


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
    product_comment: Optional[str] = Field(None, description="상품 한줄소개")


class ProductByTagRequest(BaseModel):
    """상품종류(태그)로 상품 조회 요청"""
    tag: str = Field(..., description="상품 태그(종류)", examples=["에센스&세럼&오일"])


class ProductByBrandRequest(BaseModel):
    """브랜드명으로 상품 조회 요청"""
    brand: str = Field(..., description="브랜드명", examples=["설화수"])


class ProductFilterRequest(BaseModel):
    """상품 필터링 요청"""
    # 캠페인 필터
    brands: Optional[List[str]] = Field(None, description="브랜드 리스트 (OR 조건)")
    product_categories: Optional[List[str]] = Field(None, description="상품 카테고리 리스트 (OR 조건)")
    exclusive_target: Optional[str] = Field(None, description="전용 제품")

    # 페르소나 정보 필터
    skin_type: Optional[List[str]] = Field(None, description="피부 타입 (OR 조건)")
    skin_concerns: Optional[List[str]] = Field(None, description="피부 고민 (OR 조건)")
    preferred_colors: Optional[List[str]] = Field(None, description="선호 색상 (OR 조건)")
    preferred_ingredients: Optional[List[str]] = Field(None, description="선호 성분 (OR 조건)")
    avoided_ingredients: Optional[List[str]] = Field(None, description="기피 성분 (제외 조건)")
    preferred_scents: Optional[List[str]] = Field(None, description="선호 향 (OR 조건)")
    values: Optional[List[str]] = Field(None, description="가치관 (OR 조건)")
    personal_color: Optional[str] = Field(None, description="퍼스널 컬러")
    shade_number: Optional[int] = Field(None, description="셰이드 번호")


# ============================================================
# Response Models
# ============================================================

class PersonaResponse(BaseModel):
    """페르소나 응답"""
    persona_id: str
    name: str
    created_at: Optional[datetime] = None


class PersonaDetailResponse(BaseModel):
    """페르소나 상세 정보 응답"""
    persona_id: str
    name: str
    gender: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    skin_type: Optional[List[str]] = None
    skin_concerns: Optional[List[str]] = None
    personal_color: Optional[str] = None
    shade_number: Optional[int] = None
    preferred_colors: Optional[List[str]] = None
    preferred_ingredients: Optional[List[str]] = None
    avoided_ingredients: Optional[List[str]] = None
    preferred_scents: Optional[List[str]] = None
    values: Optional[List[str]] = None
    skincare_routine: Optional[str] = None
    main_environment: Optional[str] = None
    preferred_texture: Optional[List[str]] = None
    pets: Optional[str] = None
    avg_sleep_hours: Optional[int] = None
    stress_level: Optional[str] = None
    digital_device_usage_time: Optional[int] = None
    shopping_style: Optional[str] = None
    purchase_decision_factors: Optional[List[str]] = None
    persona_created_at: Optional[datetime] = None
    ai_analysis: Optional[dict] = None


class AnalysisResultResponse(BaseModel):
    """분석 결과 응답"""
    analysis_id: int
    persona_id: str
    analysis_created_at: Optional[datetime] = None


class AnalysisResultDetailResponse(BaseModel):
    """분석 결과 상세 응답"""
    analysis_id: int
    persona_id: str
    analysis_result: str
    analysis_created_at: Optional[datetime] = None


class AnalysisResultGetRequest(BaseModel):
    """분석 결과 조회 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])


class SearchQueryResponse(BaseModel):
    """검색 쿼리 응답"""
    query_id: int
    analysis_id: int
    search_query: str
    query_created_at: Optional[datetime] = None


class SearchQueryGetRequest(BaseModel):
    """검색 쿼리 조회 요청"""
    analysis_id: int = Field(..., description="분석 ID", examples=[1])


class ProductResponse(BaseModel):
    """상품 응답"""
    product_id: str
    product_name: str
    brand: Optional[str] = None
    sale_price: Optional[int] = None
    rating: Optional[float] = None
    product_created_at: Optional[datetime] = None


class ProductDetailResponse(BaseModel):
    """상품 상세 정보 응답"""
    product_id: str
    vectordb_id: Optional[str] = None
    product_name: str
    brand: Optional[str] = None
    product_tag: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    original_price: Optional[int] = None
    discount_rate: Optional[int] = None
    sale_price: Optional[int] = None
    skin_type: Optional[List[str]] = None
    skin_concerns: Optional[List[str]] = None
    preferred_colors: Optional[List[str]] = None
    preferred_ingredients: Optional[List[str]] = None
    avoided_ingredients: Optional[List[str]] = None
    preferred_scents: Optional[List[str]] = None
    values: Optional[List[str]] = None
    exclusive_product: Optional[str] = None
    personal_color: Optional[List[str]] = None
    skin_shades: Optional[List[int]] = None
    product_image_url: Optional[List[str]] = None
    product_page_url: Optional[str] = None
    product_comment: Optional[str] = None
    product_created_at: Optional[datetime] = None


# ============================================================
# API Endpoints - POST Only
# ============================================================

class PersonaGetRequest(BaseModel):
    """페르소나 조회 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])


class PersonaQueryRequest(BaseModel):
    """Text2SQL 페르소나 쿼리 요청"""
    sql_query: str = Field(
        ...,
        description="실행할 SELECT SQL 쿼리",
        examples=["SELECT persona_id, name, skin_type FROM personas WHERE '지성' = ANY(skin_type) LIMIT 10"]
    )


@router.post("/personas", response_model=PersonaResponse, summary="페르소나 생성")
async def create_persona(request: PersonaCreate, db: Session = Depends(get_db)):
    """
    새로운 페르소나 생성

    **테이블:** personas

    **필수 필드:**
    - persona_id: 고유 ID
    - name: 이름
    """
    from core.models import Persona

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


@router.post("/personas/get", response_model=PersonaDetailResponse, summary="페르소나 정보 조회")
async def get_persona(request: PersonaGetRequest, db: Session = Depends(get_db)):
    """
    페르소나 ID로 페르소나의 전체 정보 조회

    **테이블:** personas

    **필수 필드:**
    - persona_id: 페르소나 ID

    **반환:**
    - 페르소나의 모든 상세 정보
    """
    from core.models import Persona

    # 페르소나 조회
    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

    return PersonaDetailResponse(
        persona_id=persona.persona_id,
        name=persona.name,
        gender=persona.gender,
        age=persona.age,
        occupation=persona.occupation,
        skin_type=persona.skin_type,
        skin_concerns=persona.skin_concerns,
        personal_color=persona.personal_color,
        shade_number=persona.shade_number,
        preferred_colors=persona.preferred_colors,
        preferred_ingredients=persona.preferred_ingredients,
        avoided_ingredients=persona.avoided_ingredients,
        preferred_scents=persona.preferred_scents,
        values=persona.values,
        skincare_routine=persona.skincare_routine,
        main_environment=persona.main_environment,
        preferred_texture=persona.preferred_texture,
        pets=persona.pets,
        avg_sleep_hours=persona.avg_sleep_hours,
        stress_level=persona.stress_level,
        digital_device_usage_time=persona.digital_device_usage_time,
        shopping_style=persona.shopping_style,
        purchase_decision_factors=persona.purchase_decision_factors,
        persona_created_at=persona.persona_created_at,
        ai_analysis=_build_ai_analysis(persona.persona_summary),
    )


@router.post("/personas/list", response_model=List[PersonaDetailResponse], summary="전체 페르소나 목록 조회")
async def list_personas(db: Session = Depends(get_db)):
    """
    DB에 저장된 모든 페르소나의 상세 정보 조회

    **테이블:** personas

    **반환:**
    - 모든 페르소나의 상세 정보 (생성일 기준 오름차순)
    """
    from core.models import Persona

    personas = db.query(Persona).order_by(Persona.persona_created_at.asc()).all()

    return [
        PersonaDetailResponse(
            persona_id=p.persona_id,
            name=p.name,
            gender=p.gender,
            age=p.age,
            occupation=p.occupation,
            skin_type=p.skin_type,
            skin_concerns=p.skin_concerns,
            personal_color=p.personal_color,
            shade_number=p.shade_number,
            preferred_colors=p.preferred_colors,
            preferred_ingredients=p.preferred_ingredients,
            avoided_ingredients=p.avoided_ingredients,
            preferred_scents=p.preferred_scents,
            values=p.values,
            skincare_routine=p.skincare_routine,
            main_environment=p.main_environment,
            preferred_texture=p.preferred_texture,
            pets=p.pets,
            avg_sleep_hours=p.avg_sleep_hours,
            stress_level=p.stress_level,
            digital_device_usage_time=p.digital_device_usage_time,
            shopping_style=p.shopping_style,
            purchase_decision_factors=p.purchase_decision_factors,
            persona_created_at=p.persona_created_at,
            ai_analysis=_build_ai_analysis(p.persona_summary),
        )
        for p in personas
    ]


@router.delete("/personas/{persona_id}", summary="페르소나 삭제")
async def delete_persona(persona_id: str, db: Session = Depends(get_db)):
    """
    페르소나 ID로 페르소나 삭제 (CASCADE로 연관 분석 결과도 함께 삭제)

    **테이블:** personas

    **Path 파라미터:**
    - persona_id: 삭제할 페르소나 ID
    """
    from core.models import Persona

    persona = db.query(Persona).filter(Persona.persona_id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{persona_id}' not found")

    db.delete(persona)
    db.commit()

    return {"message": f"Persona '{persona_id}' deleted successfully"}


@router.post("/personas/query", summary="Text2SQL 페르소나 쿼리")
async def query_personas_by_sql(request: PersonaQueryRequest, db: Session = Depends(get_db)) -> List[Any]:
    """
    LLM이 생성한 SQL로 페르소나 검색

    **보안 제약:**
    - SELECT 쿼리만 허용 (INSERT/UPDATE/DELETE/DROP 등 차단)
    - 결과 최대 50행 (LIMIT 없으면 자동 추가)

    **Array 컬럼 조회 예시:**
    - 단일 값 포함: `'지성' = ANY(skin_type)`
    - OR 조건: `skin_type && ARRAY['지성', '복합성']`
    - AND 조건: `skin_type @> ARRAY['비건', '친환경']`
    """
    raw_sql = request.sql_query.strip()

    # 보안 1차: SELECT로 시작하는지 검증
    if not raw_sql.upper().lstrip().startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="SELECT 쿼리만 허용됩니다. INSERT/UPDATE/DELETE/DROP 등은 사용할 수 없습니다."
        )

    # 보안 2차: 위험 키워드 검증 (단어 경계 기준)
    sql_upper = raw_sql.upper()
    dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if re.search(rf'\b{keyword}\b', sql_upper):
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않는 SQL 키워드가 포함되어 있습니다: {keyword}"
            )

    # 보안 3차: LIMIT 없으면 50 자동 추가
    if "LIMIT" not in sql_upper:
        final_sql = f"{raw_sql.rstrip(';')} LIMIT 50"
    else:
        final_sql = raw_sql.rstrip(';')

    # SQL 실행
    try:
        result = db.execute(sa_text(final_sql))
        columns = list(result.keys())
        rows = []
        for row in result.fetchall():
            row_dict = {}
            for col, val in zip(columns, row):
                if hasattr(val, 'isoformat'):
                    row_dict[col] = val.isoformat()
                else:
                    row_dict[col] = val
            rows.append(row_dict)
        return rows

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SQL 실행 중 오류가 발생했습니다: {str(e)}"
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
    from core.models import AnalysisResult, Persona

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


@router.post("/analysis-results/get", response_model=List[AnalysisResultDetailResponse], summary="분석 결과 조회")
async def get_analysis_results(request: AnalysisResultGetRequest, db: Session = Depends(get_db)):
    """
    페르소나 ID로 분석 결과 조회

    **테이블:** analysis_results

    **필수 필드:**
    - persona_id: 페르소나 ID

    **반환:**
    - 해당 페르소나의 모든 분석 결과 (시간순 정렬)
    """
    from core.models import AnalysisResult, Persona

    # 페르소나 존재 확인
    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

    # 분석 결과 조회 (최신순)
    results = db.query(AnalysisResult).filter(
        AnalysisResult.persona_id == request.persona_id
    ).order_by(AnalysisResult.analysis_created_at.desc()).all()

    return [
        AnalysisResultDetailResponse(
            analysis_id=result.analysis_id,
            persona_id=result.persona_id,
            analysis_result=result.analysis_result,
            analysis_created_at=result.analysis_created_at
        )
        for result in results
    ]


@router.post("/search-queries", response_model=SearchQueryResponse, summary="검색 쿼리 생성")
async def create_search_query(request: SearchQueryCreate, db: Session = Depends(get_db)):
    """
    검색 쿼리 생성

    **테이블:** search_queries

    **필수 필드:**
    - analysis_id: 분석 ID (FK)
    - search_query: 검색 쿼리 텍스트
    """
    from core.models import SearchQuery, AnalysisResult

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


@router.post("/search-queries/get", response_model=List[SearchQueryResponse], summary="검색 쿼리 조회")
async def get_search_queries(request: SearchQueryGetRequest, db: Session = Depends(get_db)):
    """
    분석 ID로 검색 쿼리 조회

    **테이블:** search_queries

    **필수 필드:**
    - analysis_id: 분석 ID

    **반환:**
    - 해당 분석 ID의 모든 검색 쿼리 (시간순 정렬)
    """
    from core.models import SearchQuery, AnalysisResult

    # 분석 결과 존재 확인
    analysis = db.query(AnalysisResult).filter(AnalysisResult.analysis_id == request.analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis with ID '{request.analysis_id}' not found")

    # 검색 쿼리 조회 (최신순)
    queries = db.query(SearchQuery).filter(
        SearchQuery.analysis_id == request.analysis_id
    ).order_by(SearchQuery.query_created_at.desc()).all()

    return [
        SearchQueryResponse(
            query_id=query.query_id,
            analysis_id=query.analysis_id,
            search_query=query.search_query,
            query_created_at=query.query_created_at
        )
        for query in queries
    ]


@router.post("/products", response_model=ProductResponse, summary="상품 생성")
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    """
    단일 상품 생성

    **테이블:** products

    **필수 필드:**
    - product_id: 상품 ID
    - product_name: 상품명
    """
    from core.models import Product

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


def _to_product_detail(p) -> ProductDetailResponse:
    return ProductDetailResponse(
        product_id=p.product_id,
        vectordb_id=p.vectordb_id,
        product_name=p.product_name,
        brand=p.brand,
        product_tag=p.product_tag,
        rating=float(p.rating) if p.rating is not None else None,
        review_count=p.review_count,
        original_price=p.original_price,
        discount_rate=p.discount_rate,
        sale_price=p.sale_price,
        skin_type=p.skin_type,
        skin_concerns=p.skin_concerns,
        preferred_colors=p.preferred_colors,
        preferred_ingredients=p.preferred_ingredients,
        avoided_ingredients=p.avoided_ingredients,
        preferred_scents=p.preferred_scents,
        values=p.values,
        exclusive_product=p.exclusive_product,
        personal_color=p.personal_color,
        skin_shades=p.skin_shades,
        product_image_url=p.product_image_url,
        product_page_url=p.product_page_url,
        product_comment=p.product_comment,
        product_created_at=p.product_created_at,
    )


@router.post("/products/by-tag", response_model=List[ProductDetailResponse], summary="상품종류(태그)로 상품 조회")
async def get_products_by_tag(request: ProductByTagRequest, db: Session = Depends(get_db)):
    """
    태그(상품종류)에 해당하는 모든 상품 반환.
    순위 계산은 호출 측에서 수행합니다.

    **테이블:** products

    **필수 필드:**
    - tag: 상품 태그 (product_tag 컬럼 일치)
    """
    from core.models import Product

    products = db.query(Product).filter(Product.product_tag == request.tag).all()
    return [_to_product_detail(p) for p in products]


@router.post("/products/by-brand", response_model=List[ProductDetailResponse], summary="브랜드명으로 상품 조회")
async def get_products_by_brand(request: ProductByBrandRequest, db: Session = Depends(get_db)):
    """
    브랜드명에 해당하는 모든 상품 반환.
    순위 계산은 호출 측에서 수행합니다.

    **테이블:** products

    **필수 필드:**
    - brand: 브랜드명 (brand 컬럼 일치)
    """
    from core.models import Product

    products = db.query(Product).filter(Product.brand == request.brand).all()
    return [_to_product_detail(p) for p in products]


@router.post("/products/filter", response_model=List[ProductDetailResponse], summary="상품 필터링 조회")
async def filter_products(request: ProductFilterRequest, db: Session = Depends(get_db)):
    """
    페르소나 정보와 캠페인 필터로 상품 조회

    **필터 조건:**
    - brands: 브랜드 리스트 (OR 조건 - 하나라도 일치하면 포함)
    - product_categories: 상품 카테고리 리스트 (OR 조건)
    - exclusive_target: 전용 제품 (완전 일치)
    - skin_type: 피부 타입 (OR 조건 - 배열 겹침)
    - skin_concerns: 피부 고민 (OR 조건 - 배열 겹침)
    - preferred_colors: 선호 색상 (OR 조건 - 배열 겹침)
    - preferred_ingredients: 선호 성분 (OR 조건 - 배열 겹침)
    - avoided_ingredients: 기피 성분 (제외 조건 - 배열 겹침 없음)
    - preferred_scents: 선호 향 (OR 조건 - 배열 겹침)
    - values: 가치관 (OR 조건 - 배열 겹침)
    - personal_color: 퍼스널 컬러 (배열 내 포함)
    - shade_number: 셰이드 번호 (배열 내 포함)

    **반환:** 필터 조건에 맞는 상품 리스트
    """
    from core.models import Product
    from sqlalchemy import and_, or_, cast
    from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
    from sqlalchemy.types import Text

    query = db.query(Product)

    # ========================================
    # 캠페인 필터 (AND 조건 - 필수)
    # ========================================

    # 1. 브랜드 필터
    if request.brands:
        query = query.filter(Product.brand.in_(request.brands))

    # 2. 상품 카테고리 필터
    if request.product_categories:
        query = query.filter(Product.product_tag.in_(request.product_categories))

    # 3. 전용 제품 필터
    if request.exclusive_target:
        query = query.filter(Product.exclusive_product == request.exclusive_target)

    # ========================================
    # 페르소나 필터 (OR 조건 - 하나라도 만족하면 OK)
    # ========================================

    persona_conditions = []

    # 4. 피부 타입 필터
    if request.skin_type:
        persona_conditions.append(Product.skin_type.op('&&')(cast(request.skin_type, ARRAY(Text))))

    # 5. 피부 고민 필터
    if request.skin_concerns:
        persona_conditions.append(Product.skin_concerns.op('&&')(cast(request.skin_concerns, ARRAY(Text))))

    # 6. 선호 색상 필터
    if request.preferred_colors:
        persona_conditions.append(Product.preferred_colors.op('&&')(cast(request.preferred_colors, ARRAY(Text))))

    # 7. 선호 성분 필터
    if request.preferred_ingredients:
        persona_conditions.append(Product.preferred_ingredients.op('&&')(cast(request.preferred_ingredients, ARRAY(Text))))

    # 8. 선호 향 필터
    if request.preferred_scents:
        persona_conditions.append(Product.preferred_scents.op('&&')(cast(request.preferred_scents, ARRAY(Text))))

    # 9. 가치관 필터
    if request.values:
        persona_conditions.append(Product.values.op('&&')(cast(request.values, ARRAY(Text))))

    # 10. 퍼스널 컬러 필터
    if request.personal_color:
        persona_conditions.append(Product.personal_color.op('@>')(cast([request.personal_color], ARRAY(Text))))

    # 11. 셰이드 번호 필터
    if request.shade_number:
        persona_conditions.append(Product.skin_shades.op('@>')(cast([request.shade_number], ARRAY(INTEGER))))

    # 페르소나 조건들을 OR로 결합
    if persona_conditions:
        query = query.filter(or_(*persona_conditions))

    # ========================================
    # 기피 성분 필터 (제외 조건 - AND로 적용)
    # ========================================

    # 12. 기피 성분 필터 (겹치지 않아야 함)
    if request.avoided_ingredients:
        query = query.filter(~Product.avoided_ingredients.op('&&')(cast(request.avoided_ingredients, ARRAY(Text))))

    products = query.all()
    return [_to_product_detail(p) for p in products]


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
