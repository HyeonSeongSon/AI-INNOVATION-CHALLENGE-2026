"""
대화 목록 관리 API
Claude UI 스타일 대화 세션 목록 조회/수정/삭제
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.database import SessionLocal
from core.models import Conversation

logger = logging.getLogger("conversations_api")

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


# ============================================================
# 데이터 모델
# ============================================================

class ConversationSummary(BaseModel):
    """대화 목록 항목 (messages 제외)"""
    id: str
    user_id: str
    thread_id: str
    session_id: Optional[str]
    title: str
    created_at: Optional[Any]
    last_active_at: Optional[Any]

    class Config:
        from_attributes = True


class ConversationDetail(ConversationSummary):
    """대화 상세 (messages 포함)"""
    messages: Optional[List[Any]] = []


class CreateConversationRequest(BaseModel):
    """새 대화 생성 요청"""
    user_id: str
    session_id: Optional[str] = None
    title: Optional[str] = "새 대화"


class UpdateMessagesRequest(BaseModel):
    """메시지 + 제목 갱신 요청"""
    messages: List[Any]
    title: Optional[str] = None


# ============================================================
# 엔드포인트
# ============================================================

@router.post("", status_code=201)
def create_conversation(body: CreateConversationRequest):
    """새 대화 세션 미리 생성 — 첫 메시지 전송 전 conv_id 확보용"""
    new_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        conv = Conversation(
            id=new_id,
            user_id=body.user_id,
            thread_id=new_id,
            session_id=body.session_id,
            title=body.title or "새 대화",
            messages=[],
        )
        db.add(conv)
        db.commit()
        logger.info("conversation_created | conv_id=%s", new_id)
        return {"id": new_id, "thread_id": new_id}
    finally:
        db.close()


@router.get("", response_model=List[ConversationSummary])
def list_conversations(user_id: str = Query(...)):
    """사용자의 대화 목록 조회 (최신순, messages 필드 제외)"""
    db = SessionLocal()
    try:
        convs = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.last_active_at.desc())
            .all()
        )
        return convs
    finally:
        db.close()


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    """대화 상세 조회 (messages 포함)"""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv
    finally:
        db.close()


@router.put("/{conv_id}/messages")
def update_messages(conv_id: str, body: UpdateMessagesRequest):
    """메시지 배열 및 제목 갱신"""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv.messages = body.messages
        if body.title:
            conv.title = body.title
        conv.last_active_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("conversation_messages_updated | conv_id=%s", conv_id)
        return {"status": "ok"}
    finally:
        db.close()


@router.delete("/{conv_id}")
def delete_conversation(conv_id: str):
    """대화 삭제"""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        db.delete(conv)
        db.commit()

        logger.info("conversation_deleted | conv_id=%s", conv_id)
        return {"status": "ok"}
    finally:
        db.close()
