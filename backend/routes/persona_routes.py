from fastapi import APIRouter, HTTPException
from models.persona import PersonaInput, CategoryResult
from services.persona_service import PersonaService
from utils.validators import validate_persona_logic

router = APIRouter()
persona_service = PersonaService()

@router.post("/analyze", response_model=CategoryResult)
async def analyze_persona(persona: PersonaInput):
    """
    [Flow]
    1. 데이터 검증 (Validator) -> 실패 시 400 Error
    2. 서비스 호출 (Caching -> LLM Analyze -> Logging)
    3. 결과 반환
    """
    # 1. 유효성 검사 수행
    validate_persona_logic(persona)
    
    try:
        # 2. 서비스 계층 호출
        result = await persona_service.create_persona_category(persona)
        return result
        
    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))