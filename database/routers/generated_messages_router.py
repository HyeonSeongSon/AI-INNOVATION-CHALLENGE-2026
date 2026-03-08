"""
생성된 마케팅 메시지 API
메시지 저장 및 최신 메시지 조회
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.database import SessionLocal
from core.models import Conversation, GeneratedMessage

logger = logging.getLogger("generated_messages_api")

router = APIRouter(prefix="/api/generated-messages", tags=["GeneratedMessages"])


# ============================================================
# 데이터 모델
# ============================================================

class GeneratedMessageListItem(BaseModel):
    id: str
    conversation_id: str
    product_name: Optional[str] = None
    persona_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    created_at: Optional[Any] = None
    conversation_title: Optional[str] = None

    class Config:
        from_attributes = True


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

@router.get("", response_model=List[GeneratedMessageListItem])
def list_generated_messages(
    user_id: str = Query(...),
    limit: int = Query(10),
):
    """user_id 기준 최근 생성 메시지 목록 조회 (최신순)"""
    db = SessionLocal()
    try:
        rows = (
            db.query(GeneratedMessage, Conversation.title.label("conversation_title"))
            .join(Conversation, GeneratedMessage.conversation_id == Conversation.id)
            .filter(GeneratedMessage.user_id == user_id)
            .order_by(GeneratedMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for msg, conv_title in rows:
            result.append(GeneratedMessageListItem(
                id=msg.id,
                conversation_id=msg.conversation_id,
                product_name=msg.product_name,
                persona_id=msg.persona_id,
                title=msg.title,
                content=msg.content,
                created_at=msg.created_at,
                conversation_title=conv_title,
            ))
        return result
    finally:
        db.close()


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
