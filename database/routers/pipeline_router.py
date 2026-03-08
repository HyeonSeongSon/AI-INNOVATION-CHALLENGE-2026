"""
Pipeline API Router
프론트엔드 요청을 받아 LLM 분석 + DB 저장까지 처리
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from core.models import AnalysisResult, Persona
from services.persona_analyzer import generate_persona_summary
from services.persona_analysis import run_persona_analysis

logger = logging.getLogger("pipeline")

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


class PreAnalyzeRequest(BaseModel):
    persona_id: str
    persona_data: Dict[str, Any]
    model: Optional[str] = None


# ============================================================
# 내부 함수
# ============================================================

async def _run_pre_analysis_bg(persona_id: str, persona_data: dict, model: Optional[str]) -> None:
    db = SessionLocal()
    try:
        logger.info("pre_analysis_bg_started | persona_id=%s", persona_id)

        existing = db.query(AnalysisResult).filter(
            AnalysisResult.persona_id == persona_id
        ).first()
        if existing:
            logger.info("pre_analysis_bg_skipped | persona_id=%s reason=already_exists analysis_id=%s",
                        persona_id, existing.analysis_id)
            return

        analysis_result = await run_persona_analysis(persona_data, model)

        record = AnalysisResult(
            persona_id=persona_id,
            analysis_result=json.dumps(analysis_result, ensure_ascii=False),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("pre_analysis_bg_completed | persona_id=%s analysis_id=%s", persona_id, record.analysis_id)

    except Exception as e:
        db.rollback()
        logger.error("pre_analysis_bg_failed | persona_id=%s error_type=%s error=%s",
                     persona_id, type(e).__name__, str(e), exc_info=True)
    finally:
        db.close()


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/personas/create-analyze", response_model=PersonaCreateResponse)
async def create_and_analyze_persona(
    request: PersonaCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    페르소나 생성 + AI 분석

    1. LLM으로 페르소나 요약 생성
    2. DB에 직접 저장
    3. persona_id + 분석 결과 반환
    4. 백그라운드에서 다단계×다차원 분석 사전 실행 (CRM agent 속도 향상용)
    """
    try:
        persona_data = request.model_dump(exclude={"model"})

        persona_id, persona_summary = await generate_persona_summary(
            persona_data=persona_data,
            model=request.model,
        )

        preferred_texture = persona_data.get("preferred_texture", [])
        if isinstance(preferred_texture, str):
            preferred_texture = [preferred_texture] if preferred_texture else []

        purchase_decision_factors = persona_data.get("purchase_decision_factors", [])
        if isinstance(purchase_decision_factors, str):
            purchase_decision_factors = [purchase_decision_factors] if purchase_decision_factors else []

        persona = Persona(
            persona_id=persona_id,
            name=persona_data.get("name"),
            gender=persona_data.get("gender"),
            age=persona_data.get("age"),
            occupation=persona_data.get("occupation"),
            skin_type=persona_data.get("skin_type", []),
            skin_concerns=persona_data.get("skin_concerns", []),
            personal_color=persona_data.get("personal_color"),
            shade_number=persona_data.get("shade_number"),
            preferred_colors=persona_data.get("preferred_colors", []),
            preferred_ingredients=persona_data.get("preferred_ingredients", []),
            avoided_ingredients=persona_data.get("avoided_ingredients", []),
            preferred_scents=persona_data.get("preferred_scents", []),
            values=persona_data.get("values", []),
            skincare_routine=persona_data.get("skincare_routine"),
            main_environment=persona_data.get("main_environment"),
            preferred_texture=preferred_texture,
            pets=persona_data.get("pets"),
            avg_sleep_hours=persona_data.get("avg_sleep_hours"),
            stress_level=persona_data.get("stress_level"),
            digital_device_usage_time=persona_data.get("digital_device_usage_time"),
            shopping_style=persona_data.get("shopping_style"),
            purchase_decision_factors=purchase_decision_factors,
            persona_summary=persona_summary,
        )
        db.add(persona)
        db.commit()

        persona_data_normalized = {**persona_data, "preferred_texture": preferred_texture, "purchase_decision_factors": purchase_decision_factors}
        background_tasks.add_task(_run_pre_analysis_bg, persona_id, persona_data_normalized, request.model)

        return PersonaCreateResponse(
            persona_id=persona_id,
            analysis={
                "primary_category": _extract_primary_category(persona_summary),
                "ai_analysis_text": persona_summary,
            },
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/personas/pre-analyze")
async def pre_analyze_persona(request: PreAnalyzeRequest, db: Session = Depends(get_db)):
    """
    페르소나 분석 사전 실행 (analysis_results 테이블 저장)
    이미 분석이 존재하면 skip.
    """
    try:
        existing = db.query(AnalysisResult).filter(
            AnalysisResult.persona_id == request.persona_id
        ).first()
        if existing:
            return {"status": "already_exists", "analysis_id": existing.analysis_id}

        analysis_result = await run_persona_analysis(request.persona_data, request.model)

        record = AnalysisResult(
            persona_id=request.persona_id,
            analysis_result=json.dumps(analysis_result, ensure_ascii=False),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {"status": "created", "analysis_id": record.analysis_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


def _extract_primary_category(summary: str) -> str:
    keywords = ["건성", "지성", "복합성", "민감성", "중성", "아토피"]
    for kw in keywords:
        if kw in summary:
            return f"{kw} 피부"
    return "맞춤형 뷰티"
