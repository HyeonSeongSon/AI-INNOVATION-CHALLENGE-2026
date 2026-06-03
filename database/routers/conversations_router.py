"""
대화 목록 관리 API
Claude UI 스타일 대화 세션 목록 조회/수정/삭제
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Conversation, ConversationMessage
from routers.auth_utils import get_request_user_id, resolve_role

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
    session_id: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default="새 대화", max_length=500)


class UpdateMessagesRequest(BaseModel):
    """메시지 + 제목 갱신 요청"""
    messages: List[Any] = Field(..., max_length=500)
    title: Optional[str] = Field(default=None, max_length=500)


# ============================================================
# 엔드포인트
# ============================================================

@router.post("", status_code=201)
def create_conversation(
    body: CreateConversationRequest,
    x_user_id: str = Depends(get_request_user_id),
    db: Session = Depends(get_db),
):
    """새 대화 세션 미리 생성 — 첫 메시지 전송 전 conv_id 확보용"""
    new_id = str(uuid.uuid4())
    conv = Conversation(
        id=new_id,
        user_id=x_user_id,
        thread_id=new_id,
        session_id=body.session_id,
        title=body.title or "새 대화",
    )
    db.add(conv)
    db.commit()
    logger.info("conversation_created", extra={"conv_id": new_id})
    return {"id": new_id, "thread_id": new_id}


@router.get("", response_model=List[ConversationSummary])
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    x_user_id: str = Depends(get_request_user_id),
    db: Session = Depends(get_db),
):
    """사용자의 대화 목록 조회 (최신순, messages 필드 제외 / admin은 전체 조회)"""
    role = resolve_role(db, x_user_id)
    q = db.query(Conversation)
    if role != "admin":
        q = q.filter(Conversation.user_id == x_user_id)
    return (
        q.order_by(Conversation.last_active_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    x_user_id: str = Depends(get_request_user_id),
    db: Session = Depends(get_db),
):
    """대화 상세 조회 (messages 포함, 최근 limit건)"""
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    role = resolve_role(db, x_user_id)
    if role != "admin" and conv.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    rows = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "id": conv.id,
        "user_id": conv.user_id,
        "thread_id": conv.thread_id,
        "session_id": conv.session_id,
        "title": conv.title,
        "created_at": conv.created_at,
        "last_active_at": conv.last_active_at,
        "messages": [row.message_data for row in reversed(rows)],
    }


@router.put("/{conv_id}/messages")
def update_messages(
    conv_id: str,
    body: UpdateMessagesRequest,
    x_user_id: str = Depends(get_request_user_id),
    db: Session = Depends(get_db),
):
    """메시지 배열 및 제목 갱신 (기존 메시지 삭제 후 재삽입)"""
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    role = resolve_role(db, x_user_id)
    if role != "admin" and conv.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conv_id
    ).delete()
    for msg in body.messages:
        db.add(ConversationMessage(conversation_id=conv_id, message_data=msg))
    if body.title:
        conv.title = body.title
    conv.last_active_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("conversation_messages_updated", extra={"conv_id": conv_id})
    return {"status": "ok"}


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    x_user_id: str = Depends(get_request_user_id),
    db: Session = Depends(get_db),
):
    """대화 삭제"""
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    role = resolve_role(db, x_user_id)
    if role != "admin" and conv.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    db.delete(conv)
    db.commit()

    logger.info("conversation_deleted", extra={"conv_id": conv_id})
    return {"status": "ok"}
