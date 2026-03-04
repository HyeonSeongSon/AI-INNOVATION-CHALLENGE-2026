"""
Pipeline API
프론트엔드 요청을 받아 LLM 분석 + DB 저장까지 처리
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from ..services.persona_analyzer import analyze_and_save_persona
from ..core.logging import get_logger

logger = get_logger("pipeline_api")

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])


# ============================================================
# 데이터 모델
# ============================================================

class PersonaCreateRequest(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    skin_type: Optional[List[str]] = Field(default=[])
    skin_concerns: Optional[List[str]] = Field(default=[])
    personal_color: Optional[str] = None
    shade_number: Optional[int] = None
    preferred_colors: Optional[List[str]] = Field(default=[])
    preferred_ingredients: Optional[List[str]] = Field(default=[])
    avoided_ingredients: Optional[List[str]] = Field(default=[])
    preferred_scents: Optional[List[str]] = Field(default=[])
    values: Optional[List[str]] = Field(default=[])
    skincare_routine: Optional[str] = None
    main_environment: Optional[str] = None
    preferred_texture: Optional[Any] = None
    pets: Optional[str] = None
    avg_sleep_hours: Optional[int] = None
    stress_level: Optional[str] = None
    digital_device_usage_time: Optional[int] = None
    shopping_style: Optional[str] = None
    purchase_decision_factors: Optional[Any] = None
    model: Optional[str] = None


class PersonaCreateResponse(BaseModel):
    persona_id: str
    analysis: Dict[str, Any]


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/personas/create-analyze", response_model=PersonaCreateResponse)
async def create_and_analyze_persona(request: PersonaCreateRequest):
    """
    페르소나 생성 + AI 분석

    1. LLM으로 페르소나 요약 생성
    2. Database API에 저장
    3. persona_id + 분석 결과 반환
    """
    try:
        logger.info("persona_create_analyze_start", name=request.name)

        result = await analyze_and_save_persona(
            persona_data=request.model_dump(exclude={"model"}),
            model=request.model,
        )

        return PersonaCreateResponse(
            persona_id=result["persona_id"],
            analysis={
                "primary_category": _extract_primary_category(result["persona_summary"]),
                "ai_analysis_text": result["persona_summary"],
            },
        )

    except Exception as e:
        logger.error("persona_create_analyze_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _extract_primary_category(summary: str) -> str:
    """요약 첫 문장에서 핵심 카테고리 추출 (간단 휴리스틱)"""
    keywords = ["건성", "지성", "복합성", "민감성", "중성", "아토피"]
    for kw in keywords:
        if kw in summary:
            return f"{kw} 피부"
    return "맞춤형 뷰티"
