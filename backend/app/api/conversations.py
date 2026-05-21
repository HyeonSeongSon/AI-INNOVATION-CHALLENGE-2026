"""
대화 목록 관리 API
Claude UI 스타일 대화 세션 목록 조회/수정/삭제
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.auth import UserContext
from ..core.database import get_db
from ..core.models import Conversation, ConversationMessage
from ..core.logging import get_logger
from .deps import get_current_user

logger = get_logger("conversations_api")

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

    model_config = ConfigDict(from_attributes=True)


class ConversationDetail(ConversationSummary):
    """대화 상세 (messages 포함)"""
    messages: Optional[List[Any]] = []


class CreateConversationRequest(BaseModel):
    """새 대화 생성 요청"""
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
def create_conversation(
    body: CreateConversationRequest,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """새 대화 세션 미리 생성 — 첫 메시지 전송 전 conv_id 확보용"""
    new_id = str(uuid.uuid4())
    try:
        conv = Conversation(
            id=new_id,
            user_id=current_user.user_id,
            thread_id=new_id,  # thread_id = conversation_id 고정
            session_id=body.session_id,
            title=body.title or "새 대화",
        )
        db.add(conv)
        db.commit()
        logger.info("conversation_created", conv_id=new_id, user_id=current_user.user_id)
        return {"id": new_id, "thread_id": new_id}
    except Exception as e:
        logger.error("create_conversation_failed", user_id=current_user.user_id, error=str(e))
        raise HTTPException(status_code=500, detail="대화 생성 중 오류가 발생했습니다.")


@router.get("", response_model=List[ConversationSummary])
def list_conversations(
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인증된 사용자의 대화 목록 조회 (최신순, messages 필드 제외 / admin은 전체 조회)"""
    try:
        q = db.query(Conversation)
        if current_user.role != "admin":
            q = q.filter(Conversation.user_id == current_user.user_id)
        convs = q.order_by(Conversation.last_active_at.desc()).all()
        return convs
    except Exception as e:
        logger.error("list_conversations_failed", user_id=current_user.user_id, error=str(e))
        raise HTTPException(status_code=500, detail="대화 목록 조회 중 오류가 발생했습니다.")


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: str,
    limit: int = Query(default=200, le=500),
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대화 상세 조회 (messages 포함, 최근 limit건)"""
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if current_user.role != "admin" and conv.user_id != current_user.user_id:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_conversation_failed", conv_id=conv_id, error=str(e))
        raise HTTPException(status_code=500, detail="대화 조회 중 오류가 발생했습니다.")


@router.put("/{conv_id}/messages")
def update_messages(
    conv_id: str,
    body: UpdateMessagesRequest,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """메시지 배열 및 제목 갱신 (기존 메시지 삭제 후 재삽입)"""
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if current_user.role != "admin" and conv.user_id != current_user.user_id:
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

        logger.info("conversation_messages_updated", conv_id=conv_id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_messages_failed", conv_id=conv_id, error=str(e))
        raise HTTPException(status_code=500, detail="메시지 갱신 중 오류가 발생했습니다.")


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대화 삭제"""
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if current_user.role != "admin" and conv.user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

        db.delete(conv)
        db.commit()

        logger.info("conversation_deleted", conv_id=conv_id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_conversation_failed", conv_id=conv_id, error=str(e))
        raise HTTPException(status_code=500, detail="대화 삭제 중 오류가 발생했습니다.")
