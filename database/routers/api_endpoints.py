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
    name: str = Field(..., description="이름", examples=["김지현"])
    gender: Optional[str] = Field(None, description="성별", examples=["여성"])
    age: Optional[int] = Field(None, description="나이", examples=[28])
    occupation: Optional[str] = Field(None, description="직업", examples=["마케터"])
    skin_type: Optional[List[str]] = Field(default=[], description="피부 타입", examples=[["지성", "복합성"]])
    concerns: Optional[List[str]] = Field(default=[], description="고민 (피부·헤어·기타)", examples=[["모공", "칙칙함"]])
    personal_color: Optional[str] = Field(None, description="퍼스널 컬러", examples=["웜톤"])
    shade_number: Optional[int] = Field(None, description="셰이드 번호", examples=[21])
    preferred_colors: Optional[List[str]] = Field(default=[], description="선호 색상", examples=[["코랄", "핑크"]])
    preferred_ingredients: Optional[List[str]] = Field(default=[], description="선호 성분", examples=[["히알루론산", "나이아신아마이드"]])
    avoided_ingredients: Optional[List[str]] = Field(default=[], description="기피 성분", examples=[["알코올", "파라벤"]])
    preferred_scents: Optional[List[str]] = Field(default=[], description="선호 향", examples=["플로럴"])
    lifestyle_values: Optional[List[str]] = Field(default=[], description="가치관/라이프스타일", examples=[["비건", "친환경"]])
    skincare_routine: Optional[List[str]] = Field(default=[], description="스킨케어 루틴", examples=[["간단한 루틴"]])
    main_environment: Optional[List[str]] = Field(default=[], description="주 활동 환경", examples=[["실내"]])
    preferred_texture: Optional[List[str]] = Field(default=[], description="선호 제형", examples=[["에센스", "세럼"]])
    hair_type: Optional[List[str]] = Field(default=[], description="헤어 타입", examples=[["직모", "손상모"]])
    beauty_interests: Optional[List[str]] = Field(default=[], description="관심 뷰티 카테고리", examples=[["스킨케어", "헤어"]])
    pets: Optional[List[str]] = Field(default=[], description="반려동물", examples=[["고양이"]])
    avg_sleep_hours: Optional[int] = Field(None, description="평균 수면 시간", examples=[6])
    stress_level: Optional[str] = Field(None, description="스트레스 수준", examples=["높음"])
    daily_screen_hours: Optional[int] = Field(None, description="하루 스크린 사용 시간", examples=[8])
    shopping_style: Optional[List[str]] = Field(default=[], description="쇼핑 스타일", examples=[["신중형"]])
    purchase_decision_factors: Optional[List[str]] = Field(default=[], description="구매 결정 요인", examples=[["리뷰", "성분"]])
    price_sensitivity: Optional[str] = Field(None, description="가격 민감도", examples=["가성비중시"])
    preferred_brands: Optional[List[str]] = Field(default=[], description="선호 브랜드", examples=[["설화수"]])
    avoided_brands: Optional[List[str]] = Field(default=[], description="기피 브랜드", examples=[])
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
    vectordb_id: Optional[dict] = Field(None, description="VectorDB ID (index별 doc_id 맵)")
    product_name: str = Field(..., description="상품명", examples=["수분 세럼 50ml"])
    brand: Optional[str] = Field(None, description="브랜드", examples=["설화수"])
    category: Optional[str] = Field(None, description="상품 대분류", examples=["뷰티툴"])
    tag: Optional[str] = Field(None, description="상품 중분류", examples=["마사지/전동케어"])
    sub_tag: Optional[str] = Field(None, description="상품 소분류", examples=["전동마사지기"])
    rating: Optional[float] = Field(None, description="별점", examples=[4.5])
    review_count: Optional[int] = Field(0, description="리뷰 수", examples=[128])
    original_price: Optional[int] = Field(None, description="원가", examples=[50000])
    discount_rate: Optional[int] = Field(None, description="할인율", examples=[20])
    sale_price: Optional[int] = Field(None, description="판매가", examples=[40000])
    skin_type: Optional[List[str]] = Field(default=[], description="피부 타입")
    concerns: Optional[List[str]] = Field(default=[], description="고민")
    preferred_colors: Optional[List[str]] = Field(default=[], description="선호 색상")
    preferred_ingredients: Optional[List[str]] = Field(default=[], description="선호 성분")
    avoided_ingredients: Optional[List[str]] = Field(default=[], description="기피 성분")
    preferred_scents: Optional[List[str]] = Field(default=[], description="선호 향")
    lifestyle_values: Optional[List[str]] = Field(default=[], description="가치관/라이프스타일")
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
    brands: Optional[List[str]] = Field(None, description="브랜드 리스트 (OR 조건)")
    product_categories: Optional[List[str]] = Field(None, description="상품 카테고리 리스트 (OR 조건)")
    exclusive_target: Optional[str] = Field(None, description="전용 제품")
    skin_type: Optional[List[str]] = Field(None, description="피부 타입 (OR 조건)")
    concerns: Optional[List[str]] = Field(None, description="고민 (OR 조건)")
    preferred_colors: Optional[List[str]] = Field(None, description="선호 색상 (OR 조건)")
    preferred_ingredients: Optional[List[str]] = Field(None, description="선호 성분 (OR 조건)")
    avoided_ingredients: Optional[List[str]] = Field(None, description="기피 성분 (제외 조건)")
    preferred_scents: Optional[List[str]] = Field(None, description="선호 향 (OR 조건)")
    lifestyle_values: Optional[List[str]] = Field(None, description="가치관 (OR 조건)")
    personal_color: Optional[str] = Field(None, description="퍼스널 컬러")
    shade_number: Optional[int] = Field(None, description="셰이드 번호")


# ============================================================
# Response Models
# ============================================================

class PersonaResponse(BaseModel):
    persona_id: str
    name: str
    created_at: Optional[datetime] = None


class PersonaDetailResponse(BaseModel):
    persona_id: str
    name: str
    gender: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    skin_type: Optional[List[str]] = None
    concerns: Optional[List[str]] = None
    personal_color: Optional[str] = None
    shade_number: Optional[int] = None
    preferred_colors: Optional[List[str]] = None
    preferred_ingredients: Optional[List[str]] = None
    avoided_ingredients: Optional[List[str]] = None
    preferred_scents: Optional[List[str]] = None
    lifestyle_values: Optional[List[str]] = None
    skincare_routine: Optional[List[str]] = None
    main_environment: Optional[List[str]] = None
    preferred_texture: Optional[List[str]] = None
    hair_type: Optional[List[str]] = None
    beauty_interests: Optional[List[str]] = None
    pets: Optional[List[str]] = None
    avg_sleep_hours: Optional[int] = None
    stress_level: Optional[str] = None
    daily_screen_hours: Optional[int] = None
    shopping_style: Optional[List[str]] = None
    purchase_decision_factors: Optional[List[str]] = None
    price_sensitivity: Optional[str] = None
    preferred_brands: Optional[List[str]] = None
    avoided_brands: Optional[List[str]] = None
    persona_created_at: Optional[datetime] = None
    ai_analysis: Optional[dict] = None


class AnalysisResultResponse(BaseModel):
    analysis_id: int
    persona_id: str
    analysis_created_at: Optional[datetime] = None


class AnalysisResultDetailResponse(BaseModel):
    analysis_id: int
    persona_id: str
    analysis_result: str
    analysis_created_at: Optional[datetime] = None


class AnalysisResultGetRequest(BaseModel):
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])


class SearchQueryResponse(BaseModel):
    query_id: int
    analysis_id: int
    search_query: str
    query_created_at: Optional[datetime] = None


class SearchQueryGetRequest(BaseModel):
    analysis_id: int = Field(..., description="분석 ID", examples=[1])


class ProductResponse(BaseModel):
    product_id: str
    product_name: str
    brand: Optional[str] = None
    sale_price: Optional[int] = None
    rating: Optional[float] = None
    product_created_at: Optional[datetime] = None


class ProductDetailResponse(BaseModel):
    product_id: str
    vectordb_id: Optional[dict] = None
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    sub_tag: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    original_price: Optional[int] = None
    discount_rate: Optional[int] = None
    sale_price: Optional[int] = None
    skin_type: Optional[List[str]] = None
    concerns: Optional[List[str]] = None
    preferred_colors: Optional[List[str]] = None
    preferred_ingredients: Optional[List[str]] = None
    avoided_ingredients: Optional[List[str]] = None
    preferred_scents: Optional[List[str]] = None
    lifestyle_values: Optional[List[str]] = None
    exclusive_product: Optional[str] = None
    personal_color: Optional[List[str]] = None
    skin_shades: Optional[List[int]] = None
    product_image_url: Optional[List[str]] = None
    product_page_url: Optional[str] = None
    product_comment: Optional[str] = None
    product_details: Optional[dict] = None
    product_created_at: Optional[datetime] = None


class ProductListResponse(BaseModel):
    items: List[ProductDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSearchQueryCreate(BaseModel):
    """페르소나 검색 쿼리 저장 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])
    need: str = Field(..., description="니즈 쿼리", examples=["탈모 케어 샴푸"])
    preference: str = Field(..., description="선호도 쿼리", examples=["자연 성분 샴푸"])
    retrieval: str = Field(..., description="검색 쿼리", examples=["탈모 두피 케어 샴푸 추천"])
    persona: str = Field(..., description="페르소나 쿼리", examples=["민감 두피 남성"])


class ProductSearchQueryGetRequest(BaseModel):
    """페르소나 검색 쿼리 조회 요청"""
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])


class QueryItem(BaseModel):
    query_id: int
    text: str


class ProductSearchQueryResponse(BaseModel):
    """페르소나 검색 쿼리 응답"""
    need: QueryItem
    preference: QueryItem
    retrieval: QueryItem
    persona: QueryItem


class PersonaGetRequest(BaseModel):
    persona_id: str = Field(..., description="페르소나 ID", examples=["PERSONA_001"])


class PersonaQueryRequest(BaseModel):
    sql_query: str = Field(
        ...,
        description="실행할 SELECT SQL 쿼리",
        examples=["SELECT persona_id, name, skin_type FROM personas WHERE '지성' = ANY(skin_type) LIMIT 10"]
    )


# ============================================================
# API Endpoints
# ============================================================

@router.post("/personas", response_model=PersonaResponse, summary="페르소나 생성")
async def create_persona(request: PersonaCreate, db: Session = Depends(get_db)):
    from core.models import Persona

    # persona_id는 DB가 gen_random_uuid()로 자동 생성
    persona = Persona(**request.model_dump())
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
    from core.models import Persona

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
        concerns=persona.concerns,
        personal_color=persona.personal_color,
        shade_number=persona.shade_number,
        preferred_colors=persona.preferred_colors,
        preferred_ingredients=persona.preferred_ingredients,
        avoided_ingredients=persona.avoided_ingredients,
        preferred_scents=persona.preferred_scents,
        lifestyle_values=persona.lifestyle_values,
        skincare_routine=persona.skincare_routine,
        main_environment=persona.main_environment,
        preferred_texture=persona.preferred_texture,
        hair_type=persona.hair_type,
        beauty_interests=persona.beauty_interests,
        pets=persona.pets,
        avg_sleep_hours=persona.avg_sleep_hours,
        stress_level=persona.stress_level,
        daily_screen_hours=persona.daily_screen_hours,
        shopping_style=persona.shopping_style,
        purchase_decision_factors=persona.purchase_decision_factors,
        price_sensitivity=persona.price_sensitivity,
        preferred_brands=persona.preferred_brands,
        avoided_brands=persona.avoided_brands,
        persona_created_at=persona.persona_created_at,
        ai_analysis=_build_ai_analysis(persona.persona_summary),
    )


@router.post("/personas/list", response_model=List[PersonaDetailResponse], summary="전체 페르소나 목록 조회")
async def list_personas(db: Session = Depends(get_db)):
    from core.models import Persona

    personas = db.query(Persona).order_by(Persona.persona_created_at.desc()).all()

    return [
        PersonaDetailResponse(
            persona_id=p.persona_id,
            name=p.name,
            gender=p.gender,
            age=p.age,
            occupation=p.occupation,
            skin_type=p.skin_type,
            concerns=p.concerns,
            personal_color=p.personal_color,
            shade_number=p.shade_number,
            preferred_colors=p.preferred_colors,
            preferred_ingredients=p.preferred_ingredients,
            avoided_ingredients=p.avoided_ingredients,
            preferred_scents=p.preferred_scents,
            lifestyle_values=p.lifestyle_values,
            skincare_routine=p.skincare_routine,
            main_environment=p.main_environment,
            preferred_texture=p.preferred_texture,
            hair_type=p.hair_type,
            beauty_interests=p.beauty_interests,
            pets=p.pets,
            avg_sleep_hours=p.avg_sleep_hours,
            stress_level=p.stress_level,
            daily_screen_hours=p.daily_screen_hours,
            shopping_style=p.shopping_style,
            purchase_decision_factors=p.purchase_decision_factors,
            price_sensitivity=p.price_sensitivity,
            preferred_brands=p.preferred_brands,
            avoided_brands=p.avoided_brands,
            persona_created_at=p.persona_created_at,
            ai_analysis=_build_ai_analysis(p.persona_summary),
        )
        for p in personas
    ]


@router.delete("/personas/{persona_id}", summary="페르소나 삭제")
async def delete_persona(persona_id: str, db: Session = Depends(get_db)):
    from core.models import Persona

    persona = db.query(Persona).filter(Persona.persona_id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{persona_id}' not found")

    db.delete(persona)
    db.commit()

    return {"message": f"Persona '{persona_id}' deleted successfully"}


class PersonaBulkDeleteRequest(BaseModel):
    """페르소나 일괄 삭제 요청"""
    ids: List[str] = Field(..., description="삭제할 페르소나 ID 목록")


@router.delete("/personas", summary="페르소나 일괄 삭제")
async def delete_personas_bulk(request: PersonaBulkDeleteRequest, db: Session = Depends(get_db)):
    from core.models import Persona

    if not request.ids:
        return {"deleted": 0}

    deleted = db.query(Persona).filter(Persona.persona_id.in_(request.ids)).delete(synchronize_session=False)
    db.commit()

    return {"deleted": deleted}


@router.post("/personas/query", summary="Text2SQL 페르소나 쿼리")
async def query_personas_by_sql(request: PersonaQueryRequest, db: Session = Depends(get_db)) -> List[Any]:
    raw_sql = request.sql_query.strip()

    if not raw_sql.upper().lstrip().startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="SELECT 쿼리만 허용됩니다. INSERT/UPDATE/DELETE/DROP 등은 사용할 수 없습니다."
        )

    sql_upper = raw_sql.upper()
    dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if re.search(rf'\b{keyword}\b', sql_upper):
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않는 SQL 키워드가 포함되어 있습니다: {keyword}"
            )

    if "LIMIT" not in sql_upper:
        final_sql = f"{raw_sql.rstrip(';')} LIMIT 50"
    else:
        final_sql = raw_sql.rstrip(';')

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
    from core.models import AnalysisResult, Persona

    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

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
    from core.models import AnalysisResult, Persona

    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

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
    from core.models import SearchQuery, AnalysisResult

    analysis = db.query(AnalysisResult).filter(AnalysisResult.analysis_id == request.analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis with ID '{request.analysis_id}' not found")

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
    from core.models import SearchQuery, AnalysisResult

    analysis = db.query(AnalysisResult).filter(AnalysisResult.analysis_id == request.analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis with ID '{request.analysis_id}' not found")

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


@router.post("/product-search-queries", response_model=ProductSearchQueryResponse, summary="삼품 검색 쿼리 저장")
async def generate_product_search_queries(request: ProductSearchQueryCreate, db: Session = Depends(get_db)):
    from core.models import Persona

    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

    upsert_sql = sa_text("""
        INSERT INTO search_queries (persona_id, query_type, query_text)
        VALUES (:persona_id, CAST(:query_type AS query_type_enum), :query_text)
        ON CONFLICT (persona_id, query_type)
        DO UPDATE SET query_text = EXCLUDED.query_text
        RETURNING search_query_id, query_type, query_text
    """)

    query_map = {
        "need": request.need,
        "preference": request.preference,
        "retrieval": request.retrieval,
        "persona": request.persona,
    }
    saved = {}
    for query_type, query_text in query_map.items():
        row = db.execute(upsert_sql, {"persona_id": request.persona_id, "query_type": query_type, "query_text": query_text}).fetchone()
        saved[row[1]] = {"query_id": row[0], "text": row[2]}
    db.commit()

    return ProductSearchQueryResponse(
        need=QueryItem(**saved["need"]),
        preference=QueryItem(**saved["preference"]),
        retrieval=QueryItem(**saved["retrieval"]),
        persona=QueryItem(**saved["persona"]),
    )


@router.post("/product-search-queries/get", response_model=ProductSearchQueryResponse, summary="상품 검색 쿼리 조회")
async def get_product_search_queries(request: ProductSearchQueryGetRequest, db: Session = Depends(get_db)):
    from core.models import Persona

    persona = db.query(Persona).filter(Persona.persona_id == request.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona with ID '{request.persona_id}' not found")

    result = db.execute(
        sa_text("SELECT search_query_id, query_type, query_text FROM search_queries WHERE persona_id = :persona_id"),
        {"persona_id": request.persona_id}
    )
    rows = {row[1]: {"query_id": row[0], "text": row[2]} for row in result.fetchall()}

    required = {"need", "preference", "retrieval", "persona"}
    missing = required - rows.keys()
    if missing:
        raise HTTPException(status_code=404, detail=f"검색 쿼리가 없습니다: {', '.join(sorted(missing))}")

    return ProductSearchQueryResponse(
        need=QueryItem(**rows["need"]),
        preference=QueryItem(**rows["preference"]),
        retrieval=QueryItem(**rows["retrieval"]),
        persona=QueryItem(**rows["persona"]),
    )


@router.post("/products", response_model=ProductResponse, summary="상품 생성")
async def create_product(request: ProductCreate, db: Session = Depends(get_db)):
    from core.models import Product

    existing = db.query(Product).filter(Product.product_id == request.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product with ID '{request.product_id}' already exists")

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
        category=p.category,
        tag=p.tag,
        sub_tag=p.sub_tag,
        rating=float(p.rating) if p.rating is not None else None,
        review_count=p.review_count,
        original_price=p.original_price,
        discount_rate=p.discount_rate,
        sale_price=p.sale_price,
        skin_type=p.skin_type,
        concerns=p.concerns,
        preferred_colors=p.preferred_colors,
        preferred_ingredients=p.preferred_ingredients,
        avoided_ingredients=p.avoided_ingredients,
        preferred_scents=p.preferred_scents,
        lifestyle_values=p.lifestyle_values,
        exclusive_product=p.exclusive_product,
        personal_color=p.personal_color,
        skin_shades=p.skin_shades,
        product_image_url=p.product_image_url,
        product_page_url=p.product_page_url,
        product_comment=p.product_comment,
        product_details=p.product_details,
        product_created_at=p.product_created_at,
    )


@router.get("/products", response_model=ProductListResponse, summary="상품 목록 조회 (필터/페이지네이션)")
async def list_products(
    search: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    sub_tag: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_discount: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    from core.models import Product

    query = db.query(Product)

    if search:
        query = query.filter(
            Product.product_name.ilike(f"%{search}%") | Product.product_id.ilike(f"%{search}%")
        )
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if sub_tag:
        query = query.filter(Product.sub_tag.ilike(f"%{sub_tag}%"))
    if min_price is not None:
        query = query.filter(Product.sale_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.sale_price <= max_price)
    if min_discount is not None:
        query = query.filter(Product.discount_rate >= min_discount)

    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    products = query.order_by(Product.product_created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return ProductListResponse(
        items=[_to_product_detail(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/products/{product_id}", response_model=ProductDetailResponse, summary="product_id로 상품 상세 조회")
async def get_product_by_id(product_id: str, db: Session = Depends(get_db)):
    from core.models import Product

    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with ID '{product_id}' not found")

    return _to_product_detail(product)


@router.post("/products/by-tag", response_model=List[ProductDetailResponse], summary="상품종류(소분류 태그)로 상품 조회")
async def get_products_by_tag(request: ProductByTagRequest, db: Session = Depends(get_db)):
    from core.models import Product
    products = db.query(Product).filter(Product.sub_tag == request.tag).all()
    return [_to_product_detail(p) for p in products]


@router.post("/products/by-brand", response_model=List[ProductDetailResponse], summary="브랜드명으로 상품 조회")
async def get_products_by_brand(request: ProductByBrandRequest, db: Session = Depends(get_db)):
    from core.models import Product
    products = db.query(Product).filter(Product.brand == request.brand).all()
    return [_to_product_detail(p) for p in products]


@router.post("/products/filter", response_model=List[ProductDetailResponse], summary="상품 필터링 조회")
async def filter_products(request: ProductFilterRequest, db: Session = Depends(get_db)):
    from core.models import Product
    from sqlalchemy import and_, or_, cast
    from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
    from sqlalchemy.types import Text

    query = db.query(Product)

    if request.brands:
        query = query.filter(Product.brand.in_(request.brands))

    if request.product_categories:
        query = query.filter(Product.sub_tag.in_(request.product_categories))

    if request.exclusive_target:
        query = query.filter(Product.exclusive_product == request.exclusive_target)

    persona_conditions = []

    if request.skin_type:
        persona_conditions.append(Product.skin_type.op('&&')(cast(request.skin_type, ARRAY(Text))))

    if request.concerns:
        persona_conditions.append(Product.concerns.op('&&')(cast(request.concerns, ARRAY(Text))))

    if request.preferred_colors:
        persona_conditions.append(Product.preferred_colors.op('&&')(cast(request.preferred_colors, ARRAY(Text))))

    if request.preferred_ingredients:
        persona_conditions.append(Product.preferred_ingredients.op('&&')(cast(request.preferred_ingredients, ARRAY(Text))))

    if request.preferred_scents:
        persona_conditions.append(Product.preferred_scents.op('&&')(cast(request.preferred_scents, ARRAY(Text))))

    if request.lifestyle_values:
        persona_conditions.append(Product.lifestyle_values.op('&&')(cast(request.lifestyle_values, ARRAY(Text))))

    if request.personal_color:
        persona_conditions.append(Product.personal_color.op('@>')(cast([request.personal_color], ARRAY(Text))))

    if request.shade_number:
        persona_conditions.append(Product.skin_shades.op('@>')(cast([request.shade_number], ARRAY(INTEGER))))

    if persona_conditions:
        query = query.filter(or_(*persona_conditions))

    if request.avoided_ingredients:
        query = query.filter(~Product.avoided_ingredients.op('&&')(cast(request.avoided_ingredients, ARRAY(Text))))

    products = query.all()
    return [_to_product_detail(p) for p in products]


# ============================================================
# 헬스 체크
# ============================================================

@router.get("/health", summary="API 헬스 체크")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "database": "postgresql",
        "schema_version": "1.0"
    }
