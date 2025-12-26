"""
AI Innovation Challenge 2026 - API Server
FastAPI 기반 RESTful API
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from database import get_db
from models import Brand, Product, Persona

app = FastAPI(
    title="AI Innovation Challenge 2026 API",
    description="화장품 추천 시스템 API",
    version="1.0.0"
)

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

class PersonaCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "persona_key": "user_001",
                "name": "30대 건성 피부 직장인",
                "description": "건조한 피부로 고민하는 30대 여성",
                "gender": "여성",
                "age_group": "30대",
                "skin_types": ["건성", "민감성"],
                "personal_color": "웜톤",
                "base_shade": "21호",
                "skin_concerns": ["건조", "주름", "탄력"],
                "preferred_point_colors": ["베이지", "브라운"],
                "preferred_ingredients": ["히알루론산", "세라마이드"],
                "avoided_ingredients": ["파라벤", "알코올"],
                "preferred_scents": ["무향", "플로럴"],
                "special_conditions": ["천연/유기농"],
                "budget_range": "중",
                "skincare_routine": ["기본"],
                "activity_environment": ["실내", "사무실"],
                "preferred_texture": ["크림", "로션"],
                "has_pet": ["없음"],
                "sleep_hours": "6-7시간",
                "stress_level": "보통",
                "residence_area": "도시",
                "digital_device_usage": "높음",
                "shopping_style": ["신중한", "계획적"],
                "purchase_decision_factors": ["성분", "리뷰"]
            }
        }
    )

    persona_key: str = Field(..., description="페르소나 고유 키", examples=["user_001"])
    name: str = Field(..., description="페르소나 이름", examples=["30대 건성 피부 직장인"])
    description: Optional[str] = Field(None, description="페르소나 설명", examples=["건조한 피부로 고민하는 30대 여성"])

    # 1. 기본 정보
    gender: Optional[str] = Field(None, description="성별", examples=["여성"])
    age_group: Optional[str] = Field(None, description="연령대", examples=["30대"])

    # 2. 피부 스펙
    skin_types: List[str] = Field(default=[], description="피부타입", examples=[["건성", "민감성"]])
    personal_color: Optional[str] = Field(None, description="퍼스널컬러", examples=["웜톤"])
    base_shade: Optional[str] = Field(None, description="베이스호수", examples=["21호"])

    # 3. 피부 고민
    skin_concerns: List[str] = Field(default=[], max_length=3, description="피부 고민 (최대 3개)", examples=[["건조", "주름", "탄력"]])

    # 4. 메이크업 선호
    preferred_point_colors: List[str] = Field(default=[], description="선호 포인트 컬러", examples=[["베이지", "브라운"]])

    # 5. 성분 선호
    preferred_ingredients: List[str] = Field(default=[], description="선호 성분", examples=[["히알루론산", "세라마이드"]])
    avoided_ingredients: List[str] = Field(default=[], description="기피 성분", examples=[["파라벤", "알코올"]])
    preferred_scents: List[str] = Field(default=[], description="선호 향", examples=[["무향", "플로럴"]])

    # 6. 가치관
    special_conditions: List[str] = Field(default=[], description="특수 조건", examples=[["천연/유기농"]])

    # 추가
    budget_range: Optional[str] = Field(None, description="예산 범위", examples=["중"])

    # 7. 라이프스타일 & 환경
    skincare_routine: List[str] = Field(default=[], description="스킨케어 루틴", examples=[["간단한"]])
    activity_environment: List[str] = Field(default=[], description="주 활동 환경", examples=[["실내", "사무실"]])
    preferred_texture: List[str] = Field(default=[], description="선호 제형/텍스처", examples=[["크림", "로션"]])
    has_pet: List[str] = Field(default=[], description="반려동물", examples=[["없음"]])
    sleep_hours: Optional[str] = Field(None, description="수면 시간", examples=["6-7시간"])
    stress_level: Optional[str] = Field(None, description="스트레스 수준", examples=["보통"])
    residence_area: Optional[str] = Field(None, description="거주지역", examples=["도시"])
    digital_device_usage: Optional[str] = Field(None, description="디지털 기기 사용 시간", examples=["높음"])

    # 8. 쇼핑 & 구매 성향
    shopping_style: List[str] = Field(default=[], description="쇼핑 스타일", examples=[["신중한", "계획적"]])
    purchase_decision_factors: List[str] = Field(default=[], description="구매 결정 요인", examples=[["성분", "리뷰"]])


class PersonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_key: str
    name: str
    description: Optional[str]
    gender: Optional[str]
    age_group: Optional[str]
    skin_types: List[str]
    personal_color: Optional[str]
    base_shade: Optional[str]
    skin_concerns: List[str]
    preferred_ingredients: List[str]
    avoided_ingredients: List[str]
    preferred_scents: List[str] = Field(default=[])
    preferred_point_colors: List[str] = Field(default=[])
    special_conditions: List[str] = Field(default=[])
    budget_range: Optional[str] = None

    # 라이프스타일 & 환경
    skincare_routine: List[str] = Field(default=[])
    activity_environment: List[str] = Field(default=[])
    preferred_texture: List[str] = Field(default=[])
    has_pet: List[str] = Field(default=[])
    sleep_hours: Optional[str] = None
    stress_level: Optional[str] = None
    residence_area: Optional[str] = None
    digital_device_usage: Optional[str] = None

    # 쇼핑 & 구매 성향
    shopping_style: List[str] = Field(default=[])
    purchase_decision_factors: List[str] = Field(default=[])


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None

    # 기본 정보
    product_code: Optional[str] = None
    product_name: str

    # 가격 정보
    original_price: Optional[float] = None
    discount_rate: Optional[float] = None
    sale_price: Optional[float] = None

    # 평점/리뷰
    rating: Optional[float] = None
    review_count: Optional[int] = 0

    # 페르소나 매칭 속성
    skin_types: List[str] = Field(default=[])
    personal_colors: List[str] = Field(default=[])
    base_shades: List[str] = Field(default=[])
    concern_keywords: List[str] = Field(default=[])
    makeup_colors: List[str] = Field(default=[])
    preferred_ingredients: List[str] = Field(default=[])
    avoided_ingredients: List[str] = Field(default=[])
    preferred_scents: List[str] = Field(default=[])
    values_keywords: List[str] = Field(default=[])
    dedicated_products: List[str] = Field(default=[])

    # URL 및 이미지
    product_url: Optional[str] = None
    image_urls: List[str] = Field(default=[])

    # 상세 정보
    description: Optional[str] = None
    generated_document: Optional[str] = None

    # JSONB 필드
    tags: Optional[dict] = Field(default={})
    buyer_statistics: Optional[dict] = Field(default={})


class ProductRecommendationResponse(BaseModel):
    product_id: int
    product_name: str
    brand_name: Optional[str]
    tags: Optional[dict] = Field(default={})
    sale_price: Optional[float]
    relevance_score: Optional[float]
    matched_attributes: dict
    matching_reasons: List[str]
    image_urls: List[str]


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
def root():
    """API 루트"""
    return {
        "message": "AI Innovation Challenge 2026 API",
        "version": "1.0.0",
        "endpoints": {
            "brands": "/api/brands",
            "products": "/api/products",
            "personas": "/api/personas",
            "recommendations": "/api/personas/{persona_key}/recommendations"
        }
    }


# ============================================================
# Brands API
# ============================================================

@app.get("/api/brands", tags=["Brands"])
def get_brands(db: Session = Depends(get_db)):
    """모든 브랜드 조회"""
    brands = db.query(Brand).all()
    return {
        "total": len(brands),
        "brands": [
            {
                "id": b.id,
                "name": b.name,
                "brand_url": b.brand_url,
                "tone_description": b.tone_description
            }
            for b in brands
        ]
    }


@app.get("/api/brands/{brand_id}/products", tags=["Brands"])
def get_brand_products(brand_id: int, limit: int = 20, db: Session = Depends(get_db)):
    """특정 브랜드의 상품 조회"""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    products = db.query(Product).filter(
        Product.brand_id == brand_id
    ).limit(limit).all()

    return {
        "brand": {
            "id": brand.id,
            "name": brand.name
        },
        "total": len(products),
        "products": [
            {
                "id": p.id,
                "product_name": p.product_name,
                "tags": p.tags or {},
                "sale_price": float(p.sale_price) if p.sale_price else None,
                "rating": float(p.rating) if p.rating else None,
                "image_urls": p.image_urls[:3] if p.image_urls else []
            }
            for p in products
        ]
    }


# ============================================================
# Products API
# ============================================================

@app.get("/api/products", tags=["Products"])
def get_products(
    limit: int = 20,
    offset: int = 0,
    product_name: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    상품 목록 조회
    - product_name: 상품명으로 검색 (부분 일치)
    - tag: tags JSONB 필드에서 검색
    """
    query = db.query(Product).options(joinedload(Product.brand))

    if product_name:
        query = query.filter(Product.product_name.ilike(f"%{product_name}%"))

    if tag:
        # JSONB tags 필드에서 검색 (값이 배열인 경우와 문자열인 경우 모두 지원)
        query = query.filter(
            text(f"tags::text ILIKE :tag")
        ).params(tag=f"%{tag}%")

    total = query.count()
    products = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters": {
            "product_name": product_name,
            "tag": tag
        },
        "products": [
            {
                "id": p.id,
                "product_name": p.product_name,
                "brand_name": p.brand.name if p.brand else None,
                "tags": p.tags or {},
                "sale_price": float(p.sale_price) if p.sale_price else None,
                "rating": float(p.rating) if p.rating else None,
                "review_count": p.review_count or 0,
                "image_urls": p.image_urls[:3] if p.image_urls else [],
                "description": p.description
            }
            for p in products
        ]
    }


@app.get("/api/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    """특정 상품 상세 조회 (모든 필드 포함)"""
    product = db.query(Product).options(
        joinedload(Product.brand)
    ).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductResponse(
        id=product.id,
        brand_id=product.brand_id,
        brand_name=product.brand.name if product.brand else None,
        product_code=product.product_code,
        product_name=product.product_name,
        original_price=float(product.original_price) if product.original_price else None,
        discount_rate=float(product.discount_rate) if product.discount_rate else None,
        sale_price=float(product.sale_price) if product.sale_price else None,
        rating=float(product.rating) if product.rating else None,
        review_count=product.review_count or 0,
        skin_types=product.skin_types or [],
        personal_colors=product.personal_colors or [],
        base_shades=product.base_shades or [],
        concern_keywords=product.concern_keywords or [],
        makeup_colors=product.makeup_colors or [],
        preferred_ingredients=product.preferred_ingredients or [],
        avoided_ingredients=product.avoided_ingredients or [],
        preferred_scents=product.preferred_scents or [],
        values_keywords=product.values_keywords or [],
        dedicated_products=product.dedicated_products or [],
        product_url=product.product_url,
        image_urls=product.image_urls or [],
        description=product.description,
        generated_document=product.generated_document,
        tags=product.tags or {},
        buyer_statistics=product.buyer_statistics or {}
    )


# ============================================================
# Personas API
# ============================================================

@app.post("/api/personas", response_model=PersonaResponse, tags=["Personas"])
def create_persona(persona_data: PersonaCreate, db: Session = Depends(get_db)):
    """
    새 페르소나 생성
    프론트엔드에서 사용자 정보를 받아서 페르소나로 저장
    """
    # 중복 확인
    existing = db.query(Persona).filter(
        Persona.persona_key == persona_data.persona_key
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Persona with key '{persona_data.persona_key}' already exists"
        )

    # 새 페르소나 생성
    persona = Persona(**persona_data.dict())
    db.add(persona)
    db.commit()
    db.refresh(persona)

    return persona


@app.get("/api/personas", tags=["Personas"])
def get_personas(db: Session = Depends(get_db)):
    """모든 페르소나 조회"""
    personas = db.query(Persona).all()

    return {
        "total": len(personas),
        "personas": [
            {
                "id": p.id,
                "persona_key": p.persona_key,
                "name": p.name,
                "gender": p.gender,
                "age_group": p.age_group,
                "skin_types": p.skin_types,
                "skin_concerns": p.skin_concerns,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in personas
        ]
    }


@app.get("/api/personas/{persona_key}", response_model=PersonaResponse, tags=["Personas"])
def get_persona(persona_key: str, db: Session = Depends(get_db)):
    """특정 페르소나 조회"""
    persona = db.query(Persona).filter(
        Persona.persona_key == persona_key
    ).first()

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    return persona


@app.put("/api/personas/{persona_key}", response_model=PersonaResponse, tags=["Personas"])
def update_persona(
    persona_key: str,
    persona_data: PersonaCreate,
    db: Session = Depends(get_db)
):
    """페르소나 정보 업데이트"""
    persona = db.query(Persona).filter(
        Persona.persona_key == persona_key
    ).first()

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # 업데이트
    for key, value in persona_data.dict(exclude_unset=True).items():
        setattr(persona, key, value)

    db.commit()
    db.refresh(persona)

    return persona


@app.delete("/api/personas/{persona_key}", tags=["Personas"])
def delete_persona(persona_key: str, db: Session = Depends(get_db)):
    """페르소나 삭제"""
    persona = db.query(Persona).filter(
        Persona.persona_key == persona_key
    ).first()

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    db.delete(persona)
    db.commit()

    return {"message": f"Persona '{persona_key}' deleted successfully"}


# ============================================================
# Recommendations API
# ============================================================

@app.get("/api/personas/{persona_key}/recommendations", tags=["Recommendations"])
def get_persona_recommendations(
    persona_key: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    특정 페르소나에 맞는 추천 상품 조회
    TODO: 추천 알고리즘 구현 필요
    """
    # 페르소나 확인
    persona = db.query(Persona).filter(
        Persona.persona_key == persona_key
    ).first()

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # TODO: 추천 로직 구현
    # 현재는 빈 배열 반환
    return {
        "persona": {
            "persona_key": persona.persona_key,
            "name": persona.name,
            "skin_concerns": persona.skin_concerns,
            "preferred_ingredients": persona.preferred_ingredients
        },
        "total": 0,
        "recommendations": [],
        "message": "Recommendation algorithm not implemented yet"
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
        brand_count = db.query(Brand).count()
        product_count = db.query(Product).count()
        persona_count = db.query(Persona).count()

        return {
            "status": "healthy",
            "database": "connected",
            "tables": {
                "brands": brand_count,
                "products": product_count,
                "personas": persona_count
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
