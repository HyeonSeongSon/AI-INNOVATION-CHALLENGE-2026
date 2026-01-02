from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import json
import uuid

# DB 관련
from database import get_db
from database.models import Persona, AnalysisResult 

# AI 서비스
from app.service.ai_service import PersonaAIService

router = APIRouter(prefix="/pipeline")
ai_service = PersonaAIService()

# ---------------------------------------------------------
# [DTO] 데이터 구조
# ---------------------------------------------------------
class PersonaCreateRequest(BaseModel):
    name: str
    age: int
    gender: str
    occupation: Optional[str] = None
    skin_type: List[str] = []
    skin_concerns: List[str] = []
    personal_color: Optional[str] = None
    shade_number: Optional[int] = 21
    preferred_colors: List[str] = []
    preferred_ingredients: List[str] = []
    avoided_ingredients: List[str] = []
    preferred_scents: List[str] = []
    skincare_routine: Optional[str] = None
    main_environment: Optional[str] = None
    preferred_texture: List[str] = []
    pets: Optional[str] = None
    digital_device_usage_time: Optional[int] = 0
    avg_sleep_hours: Optional[int] = 0
    stress_level: Optional[str] = None
    shopping_style: Optional[str] = None
    purchase_decision_factors: List[str] = []
    values: List[str] = []
    full_raw_data: Optional[Dict[str, Any]] = {}


# ---------------------------------------------------------
# [API 1] 조회 (GET) - ✅ 에러 수정됨
# ---------------------------------------------------------
@router.get("/personas")
def get_personas(db: Session = Depends(get_db)):
    """
    저장된 모든 페르소나 목록 조회
    """
    try:
        # ✅ [수정] models.py에 정의된 컬럼명(persona_created_at) 사용
        personas = db.query(Persona).order_by(Persona.persona_created_at.desc()).all()
        result = []
        
        for p in personas:
            # 최신 분석 결과 조회
            analysis = db.query(AnalysisResult).filter(
                AnalysisResult.persona_id == p.persona_id
            ).order_by(AnalysisResult.analysis_created_at.desc()).first()
            
            ai_data = {}
            if analysis and analysis.analysis_result:
                try:
                    ai_data = json.loads(analysis.analysis_result)
                except:
                    ai_data = {}

            result.append({
                "persona_id": p.persona_id,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
                "occupation": p.occupation,
                
                "skin_type": p.skin_type,
                "skin_concerns": p.skin_concerns,
                "personal_color": p.personal_color,
                "shade_number": p.shade_number,
                
                "preferred_colors": p.preferred_colors,
                "preferred_ingredients": p.preferred_ingredients,
                "avoided_ingredients": p.avoided_ingredients,
                "preferred_scents": p.preferred_scents,
                
                "skincare_routine": p.skincare_routine,
                "main_environment": p.main_environment,
                "preferred_texture": p.preferred_texture,
                
                "pets": p.pets,
                "avg_sleep_hours": p.avg_sleep_hours,
                "stress_level": p.stress_level,
                "digital_device_usage_time": p.digital_device_usage_time,
                "shopping_style": p.shopping_style,
                "purchase_decision_factors": p.purchase_decision_factors,
                "values": p.values,
                
                "ai_analysis": {
                    "primary_category": ai_data.get('primary_category'),
                    "ai_analysis_text": ai_data.get('ai_analysis_text'),
                    "tagging_keywords": ai_data.get('tagging_keywords')
                }
            })
        return result
        
    except Exception as e:
        print(f"❌ Get Personas Error: {e}")
        return []


# ---------------------------------------------------------
# [API 2] 생성 (POST)
# ---------------------------------------------------------
@router.post("/personas/create-analyze")
async def create_and_analyze_persona(req: PersonaCreateRequest, db: Session = Depends(get_db)):
    try:
        data = req.dict()
        new_persona_id = str(uuid.uuid4())
        
        new_persona = Persona(
            persona_id=new_persona_id,
            name=data.get('name'),
            age=data.get('age'),
            gender=data.get('gender'),
            occupation=data.get('occupation'),
            skin_type=data.get('skin_type', []),
            skin_concerns=data.get('skin_concerns', []),
            personal_color=data.get('personal_color'),
            shade_number=data.get('shade_number'),
            preferred_colors=data.get('preferred_colors', []),
            preferred_ingredients=data.get('preferred_ingredients', []),
            avoided_ingredients=data.get('avoided_ingredients', []),
            preferred_scents=data.get('preferred_scents', []),
            skincare_routine=data.get('skincare_routine'),
            main_environment=data.get('main_environment'),
            preferred_texture=data.get('preferred_texture', []),
            pets=data.get('pets'),
            avg_sleep_hours=data.get('avg_sleep_hours'),
            stress_level=data.get('stress_level'),
            digital_device_usage_time=data.get('digital_device_usage_time'),
            shopping_style=data.get('shopping_style'),
            purchase_decision_factors=data.get('purchase_decision_factors', []),
            values=data.get('values', [])
        )
        db.add(new_persona)
        db.commit()
        db.refresh(new_persona)

        # AI 분석
        analysis_data = await ai_service.analyze_profile(data)
        
        # 분석 결과 저장
        final_analysis_json = {
            "tagging_keywords": analysis_data.get('tagging_keywords', []),
            "ai_analysis_text": analysis_data.get('ai_analysis_text', ''),
            "primary_category": analysis_data.get('primary_category', 'ETC')
        }

        new_analysis = AnalysisResult(
            persona_id=new_persona_id,
            analysis_result=json.dumps(final_analysis_json, ensure_ascii=False)
        )
        db.add(new_analysis)
        db.commit()

        return {
            "status": "success",
            "persona_id": new_persona.persona_id,
            "name": new_persona.name,
            "analysis": {
                "primary_category": analysis_data.get('primary_category'),
                "ai_analysis_text": analysis_data.get('ai_analysis_text'),
                "tagging_keywords": analysis_data.get('tagging_keywords')
            }
        }

    except Exception as e:
        db.rollback()
        print(f"❌ Pipeline Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# [API 3] 삭제 (DELETE)
# ---------------------------------------------------------
@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: str, db: Session = Depends(get_db)):
    try:
        persona = db.query(Persona).filter(Persona.persona_id == persona_id).first()
        
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        db.delete(persona)
        db.commit()
        return {"status": "success", "message": f"Persona {persona_id} deleted"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))