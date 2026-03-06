"""
생성된 마케팅 메시지 API
메시지 저장 및 최신 메시지 조회
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core.database import SessionLocal
from ..core.models import GeneratedMessage
from ..core.logging import get_logger

logger = get_logger("generated_messages_api")

router = APIRouter(prefix="/api/generated-messages", tags=["GeneratedMessages"])


# ============================================================
# 데이터 모델
# ============================================================

class GeneratedMessageResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    product_id: str
    product_name: Optional[str] = None
    persona_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    thread_id: Optional[str] = None
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True


# ============================================================
# 엔드포인트
# ============================================================

@router.get("/latest", response_model=GeneratedMessageResponse)
def get_latest(
    conversation_id: str = Query(...),
    product_id: str = Query(...),
):
    """conversation_id + product_id 기준 가장 최근 생성 메시지 조회"""
    db = SessionLocal()
    try:
        msg = (
            db.query(GeneratedMessage)
            .filter(
                GeneratedMessage.conversation_id == conversation_id,
                GeneratedMessage.product_id == product_id,
            )
            .order_by(GeneratedMessage.created_at.desc())
            .first()
        )
        if not msg:
            raise HTTPException(status_code=404, detail="No generated message found")
        return msg
    finally:
        db.close()
