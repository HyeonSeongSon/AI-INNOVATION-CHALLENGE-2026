import json
import uuid
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, or_
from pydantic import BaseModel

# ✅ 경로 및 모델 확인 (SearchQuery 포함)
from database import get_db, init_db
from db_models import Persona, AnalysisResult, SearchQuery, Product, Brand
from services.ai_service import PersonaAIService 

ai_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 초기화
    try:
        init_db()
        print("✅ PostgreSQL 데이터베이스 준비 완료")
    except Exception as e:
        print(f"❌ DB 초기화 실패: {e}")
    
    # 2. AI 서비스 로드
    global ai_service
    ai_service = PersonaAIService()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# [Part 1] 페르소나 관리 API
# ============================================================

# ✅ 프론트엔드 데이터 구조 수용 (매핑 전)
class PersonaCreateRequest(BaseModel):
    name: str
    age: int
    gender: str
    occupation: Optional[str] = None
    
    # 프론트엔드 키값 -> DB 컬럼 매핑 필요
    skin_type: List[str] = []
    concern_keywords: List[str] = []         # DB: skin_concerns
    personal_color: Optional[str] = None
    base_shade: Optional[str] = None         # DB: shade_number (int)
    preferred_makeup_colors: List[str] = []  # DB: preferred_colors
    preferred_ingredients: List[str] = []
    avoided_ingredients: List[str] = []
    preferred_scent: Optional[str] = None    # DB: preferred_scents (List)
    routine_type: Optional[str] = None       # DB: skincare_routine
    activity_environment: Optional[str] = None # DB: main_environment
    preferred_texture: List[str] = []
    pet_type: Optional[str] = None           # DB: pets
    digital_device_hours: Optional[int] = 0  # DB: digital_device_usage_time
    sleep_hours: Optional[str] = None        # DB: avg_sleep_hours (int)
    stress_level: Optional[str] = None
    shopping_style: Optional[str] = None
    purchase_factor: Optional[str] = None    # DB: purchase_decision_factors (List)
    values: Optional[str] = None             # DB: values (List)
    
    full_raw_data: Optional[Dict[str, Any]] = {}


@app.post("/api/personas")
async def create_persona_pipeline(req: PersonaCreateRequest, db: Session = Depends(get_db)):
    """페르소나 생성 + AI 분석 파이프라인"""
    if not ai_service: raise HTTPException(503, "AI Service Not Ready")

    try:
        data = req.dict()

        # ---------------------------------------------------------
        # 1. 데이터 타입 변환 및 매핑 (Frontend -> DB Schema)
        # ---------------------------------------------------------
        
        # (1) 문자열 -> 리스트 변환
        scent_list = [data.get('preferred_scent')] if data.get('preferred_scent') else []
        
        # "A, B" 형태의 문자열 -> 리스트로 분리
        values_str = data.get('values') or ""
        values_list = [v.strip() for v in values_str.split(',')] if values_str else []
        
        purchase_str = data.get('purchase_factor') or ""
        purchase_list = [v.strip() for v in purchase_str.split(',')] if purchase_str else []

        # (2) 문자열 -> 정수 변환 안전 처리
        def safe_int(val):
            try:
                return int(val) if val is not None and str(val).isdigit() else None
            except:
                return None

        shade_num = safe_int(data.get('base_shade'))
        sleep_num = safe_int(data.get('sleep_hours'))

        # ---------------------------------------------------------
        # 2. DB 저장 (New Schema: Persona)
        # ---------------------------------------------------------
        new_persona = Persona(
            # persona_id는 DB 모델에서 UUID 자동 생성
            name=data.get('name') or 'Unknown',
            gender=data.get('gender'),
            age=data.get('age'),
            occupation=data.get('occupation'),
            
            # 배열 컬럼 매핑
            skin_type=data.get('skin_type', []),
            skin_concerns=data.get('concern_keywords', []), # 매핑
            
            personal_color=data.get('personal_color'),
            shade_number=shade_num, # 매핑
            
            preferred_colors=data.get('preferred_makeup_colors', []), # 매핑
            preferred_ingredients=data.get('preferred_ingredients', []),
            avoided_ingredients=data.get('avoided_ingredients', []),
            preferred_scents=scent_list, # 매핑
            
            values=values_list, # 매핑
            
            skincare_routine=data.get('routine_type'), # 매핑
            main_environment=data.get('activity_environment'), # 매핑
            preferred_texture=data.get('preferred_texture', []),
            pets=data.get('pet_type'), # 매핑
            
            avg_sleep_hours=sleep_num, # 매핑
            stress_level=data.get('stress_level'),
            digital_device_usage_time=data.get('digital_device_hours', 0), # 매핑
            
            shopping_style=data.get('shopping_style'),
            purchase_decision_factors=purchase_list # 매핑
        )
        
        db.add(new_persona)
        db.commit()
        db.refresh(new_persona)

        # ---------------------------------------------------------
        # 3. AI 분석 실행 & 결과 저장
        # ---------------------------------------------------------
        analysis_data = await ai_service.analyze_profile(data)
        
        new_analysis = AnalysisResult(
            persona_id=new_persona.persona_id, # UUID String
            analysis_result=analysis_data.get('ai_analysis_text', '분석 대기중')
        )
        db.add(new_analysis)
        db.commit()
        db.refresh(new_analysis)

        return {
            "status": "success",
            "persona_id": new_persona.persona_id,
            "data": {
                "name": new_persona.name,
                "category": analysis_data.get('primary_category'),
                "analysis_text": new_analysis.analysis_result,
                "solution_guide": "상세 분석 결과가 저장되었습니다."
            }
        }
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/personas")
def get_personas_list(db: Session = Depends(get_db)):
    """페르소나 목록 조회 (DB -> Frontend 역매핑)"""
    # 최신순 정렬 (persona_created_at 기준)
    personas = db.query(Persona).order_by(Persona.persona_created_at.desc()).all()
    result = []
    
    for p in personas:
        # 최신 분석 결과 가져오기
        latest_analysis = p.analysis_results[-1] if p.analysis_results else None
        
        # DB 컬럼 -> 프론트엔드 키 역매핑
        result.append({
            "id": p.persona_id, # 프론트엔드 식별자
            "name": p.name,
            "age": p.age,
            "gender": p.gender,
            "occupation": p.occupation,
            
            "skin_types": p.skin_type,
            "concern_keywords": p.skin_concerns, # 역매핑
            
            "personal_color": p.personal_color,
            "base_shade": str(p.shade_number) if p.shade_number is not None else "",
            
            "preferred_makeup_colors": p.preferred_colors,
            "preferred_ingredients": p.preferred_ingredients,
            "avoided_ingredients": p.avoided_ingredients,
            "preferred_scent": p.preferred_scents[0] if p.preferred_scents else "",
            
            "routine_type": p.skincare_routine,
            "environment": p.main_environment,
            "texture": p.preferred_texture,
            "pet_type": p.pets,
            
            "sleep_hours": str(p.avg_sleep_hours) if p.avg_sleep_hours is not None else "",
            "stress_level": p.stress_level,
            "digital_device_hours": p.digital_device_usage_time,
            
            "shopping_style": p.shopping_style,
            "buying_factor": p.purchase_decision_factors,
            "values": ", ".join(p.values) if p.values else "",
            
            "aiAnalysis": {
                "reasoning": latest_analysis.analysis_result if latest_analysis else "분석 대기중",
                "primary_category": "AI ANALYSIS" 
            }
        })
    return result

# ============================================================
# [Part 2] 쇼핑몰 API
# ============================================================

@app.get("/api/brands", tags=["Brands"])
def get_brands(db: Session = Depends(get_db)):
    """모든 브랜드 조회"""
    brands = db.query(Brand).all()
    return {"total": len(brands), "brands": [{"id": b.id, "name": b.name} for b in brands]}

@app.get("/api/products", tags=["Products"])
def get_products(
    limit: int = 20,
    offset: int = 0,
    product_name: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """상품 목록 조회"""
    query = db.query(Product) 

    if product_name:
        query = query.filter(Product.product_name.ilike(f"%{product_name}%"))
    
    if tag:
        # product_tag 컬럼이 문자열이라고 가정 (테이블 스펙상 varchar)
        query = query.filter(Product.product_tag.ilike(f"%{tag}%"))

    total = query.count()
    products = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "products": [
            {
                "id": p.product_id, # String ID
                "product_name": p.product_name,
                "brand_name": p.brand or "AMORE", 
                "sale_price": float(p.sale_price) if p.sale_price else 0,
                "rating": float(p.rating) if p.rating else 0.0,
                # product_image_url이 배열(List)이므로 첫 번째 것만 가져옴
                "image_urls": p.product_image_url[:1] if p.product_image_url else [], 
                "tags": [p.product_tag] if p.product_tag else []
            }
            for p in products
        ]
    }

# ============================================================
# [Part 3] AI 추천 API (+ 검색 로그 저장)
# ============================================================

class RecommendRequest(BaseModel):
    persona_id: str # UUID String으로 변경됨
    purpose: str = "제품 추천"
    category: Optional[str] = None 
    season: Optional[str] = None 

@app.post("/api/recommend")
async def recommend_product_type(req: RecommendRequest, db: Session = Depends(get_db)):
    """AI 추천 + DB 상품 검색 + 결과 로그 저장"""
    
    # 1. 페르소나 조회
    persona = db.query(Persona).filter(Persona.persona_id == req.persona_id).first()
    if not persona: raise HTTPException(404, "Not Found")
    
    # 2. AI 분석 결과 조회 (FK 연결용)
    last_analysis = db.query(AnalysisResult).filter(AnalysisResult.persona_id == persona.persona_id).order_by(AnalysisResult.analysis_id.desc()).first()
    
    # 3. AI 서비스 호출
    # 필요한 데이터만 추출해서 넘김
    raw_data_mock = {
        "preferred_texture": persona.preferred_texture,
        "concern_keywords": persona.skin_concerns
    }
    
    # ✅ purpose, category, season을 AI에게 전달
    rec_text = await ai_service.recommend_product_type(
        analysis_result={
            "tagging_keywords": persona.skin_concerns, 
            "ai_analysis_text": last_analysis.analysis_result if last_analysis else ""
        },
        raw_data=raw_data_mock,
        purpose=req.purpose,    
        category=req.category,  
        season=req.season       
    )
    
    # 🌟 4. [검색 로그 저장] SearchQuery 테이블에 결과 기록
    if last_analysis:
        ai_answer = rec_text.get("detailed_solution", "결과 없음")
        
        # [형식] 요청 조건과 AI 답변을 합쳐서 저장
        log_content = f"""[요청] 목적:{req.purpose}, 카테고리:{req.category}, 시즌:{req.season}
[AI추천] {ai_answer}"""
        
        new_query_log = SearchQuery(
            analysis_id=last_analysis.analysis_id,
            search_query=log_content # 여기에 전체 로그 저장
        )
        db.add(new_query_log)
        db.commit()

    # 5. DB 상품 검색
    found_products = []
    search_keyword = req.category if req.category else "스킨케어"
    
    # 이름이나 태그로 검색
    products_query = db.query(Product).filter(
        or_(
            Product.product_name.ilike(f"%{search_keyword}%"),
            Product.product_tag.ilike(f"%{search_keyword}%")
        )
    ).limit(3).all()
    
    for p in products_query:
        found_products.append({
            "id": p.product_id,
            "product_name": p.product_name,
            "brand_name": p.brand or "AMORE",
            "sale_price": float(p.sale_price) if p.sale_price else 0,
            "image_urls": p.product_image_url,
            "tags": [p.product_tag] if p.product_tag else []
        })
    
    return {
        "status": "success",
        "reasoning": rec_text.get("detailed_solution", "추천 가이드 생성 완료"),
        "products": found_products 
    }

# ✅ ChatMessage 관련 API는 삭제되었습니다. (로컬 스토리지 사용)