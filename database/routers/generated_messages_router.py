"""
생성된 마케팅 메시지 API
메시지 저장 및 최신 메시지 조회
"""

import logging
from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
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
    title: Optional[str] = None
    content: str
    thread_id: Optional[str] = None
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True


class GeneratedMessageFilterItem(BaseModel):
    id: str
    product_name: Optional[str] = None
    brand: Optional[str] = None
    sub_tag: Optional[str] = None
    purpose: Optional[str] = None
    title: Optional[str] = None
    content: str
    quality_passed: Optional[bool] = None
    llm_score_overall: Optional[float] = None
    llm_feedback: Optional[str] = None
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True


class GeneratedMessageFilterResponse(BaseModel):
    total: int
    items: List[GeneratedMessageFilterItem]


class FilterOptions(BaseModel):
    brands: List[str]
    product_tags: List[str]
    purposes: List[str]


# ============================================================
# 엔드포인트
# ============================================================

@router.get("/filter-options", response_model=FilterOptions)
def get_filter_options(user_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """user_id 기준 필터 드롭다운용 distinct 값 목록 조회 (user_id 없으면 전체)"""
    def _distinct_values(col):
        q = db.query(col).filter(col.isnot(None), col != "")
        if user_id:
            q = q.filter(GeneratedMessage.user_id == user_id)
        rows = q.distinct().all()
        return sorted([r[0] for r in rows])

    brands = _distinct_values(GeneratedMessage.brand)
    product_tags = _distinct_values(GeneratedMessage.sub_tag)
    purposes = _distinct_values(GeneratedMessage.purpose)

    return FilterOptions(brands=brands, product_tags=product_tags, purposes=purposes)


@router.get("", response_model=GeneratedMessageFilterResponse)
def list_generated_messages(
    user_id: Optional[str] = Query(None),
    limit: int = Query(20),
    offset: int = Query(0),
    brand: Optional[str] = Query(None),
    sub_tag: Optional[str] = Query(None),
    purpose: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """생성 메시지 목록 조회 (user_id 없으면 전체, 있으면 해당 사용자만)"""
    query = db.query(GeneratedMessage)
    if user_id:
        query = query.filter(GeneratedMessage.user_id == user_id)

    if brand:
        query = query.filter(GeneratedMessage.brand == brand)
    if sub_tag:
        query = query.filter(GeneratedMessage.sub_tag == sub_tag)
    if purpose:
        query = query.filter(GeneratedMessage.purpose == purpose)
    if start_date:
        query = query.filter(GeneratedMessage.created_at >= start_date)
    if end_date:
        query = query.filter(GeneratedMessage.created_at < end_date + timedelta(days=1))

    total = query.count()
    rows = (
        query
        .order_by(GeneratedMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        GeneratedMessageFilterItem(
            id=msg.id,
            product_name=msg.product_name,
            brand=msg.brand,
            sub_tag=msg.sub_tag,
            purpose=msg.purpose,
            title=msg.title,
            content=msg.content,
            quality_passed=msg.quality_passed,
            llm_score_overall=float(msg.llm_score_overall) if msg.llm_score_overall is not None else None,
            llm_feedback=msg.llm_feedback,
            created_at=msg.created_at,
        )
        for msg in rows
    ]
    return GeneratedMessageFilterResponse(total=total, items=items)


@router.delete("")
def delete_messages(ids: List[str] = Body(..., embed=True), db: Session = Depends(get_db)):
    """선택한 메시지 ID 목록 일괄 삭제"""
    if not ids:
        return {"deleted": 0}
    deleted = (
        db.query(GeneratedMessage)
        .filter(GeneratedMessage.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.get("/latest", response_model=GeneratedMessageResponse)
def get_latest(
    conversation_id: str = Query(...),
    product_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """conversation_id + product_id 기준 가장 최근 생성 메시지 조회"""
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
