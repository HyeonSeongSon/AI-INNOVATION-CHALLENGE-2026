"""
Marketing Agent API 엔드포인트
Supervisor + CRM subgraph 기반
"""

import uuid
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any

from ..agents.supervisor.marketing_agent import MarketingAgent
from ..core.logging import get_logger
from ..core.database import SessionLocal
from ..core.models import Conversation, GeneratedMessage

logger = get_logger("marketing_api")

router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


def get_agent(request: Request) -> MarketingAgent:
    return request.app.state.agent


# ============================================================
# 인증 의존성
# ============================================================

async def get_current_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """
    X-User-Id 헤더에서 user_id 추출.

    현재는 헤더 값을 그대로 사용하는 플레이스홀더입니다.
    추후 JWT 검증으로 교체:
        token = Header(..., alias="Authorization")
        payload = jwt.decode(token.removeprefix("Bearer "), SECRET_KEY, ...)
        return payload["sub"]
    """
    return x_user_id


# ============================================================
# 데이터 모델
# ============================================================

class ChatRequest(BaseModel):
    """대화 요청 (신규 + 이어가기 통합)"""
    user_input: str
    session_id: str                       # 프론트에서 생성한 채팅 세션 ID
    thread_id: Optional[str] = None       # 없으면 신규 대화, 있으면 기존 대화 이어가기
    conversation_id: Optional[str] = None # 없으면 신규 대화 레코드 생성
    model: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "user_input": "PERSONA_001로 설화수 크림 신상품 홍보 메시지 만들어줘",
                "session_id": "sess_abc123",
                "thread_id": None,
                "model": "gpt-4o-mini"
            }
        }


class ResumeRequest(BaseModel):
    """
    Interrupt 재개 요청 (모든 interrupt 타입 통합)

    interrupt_type으로 어떤 interrupt인지 명시하고,
    payload에 interrupt 타입별 데이터를 담습니다.

    현재 지원 타입:
        - "product_selection": payload = {"selected_product_id": "PROD001"}
    """
    thread_id: str
    session_id: str
    interrupt_type: str              # "product_selection" | 미래 타입들
    payload: Dict[str, Any]          # interrupt 타입별 데이터
    conversation_id: Optional[str] = None  # DB 저장용
    model: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "thread_id": "uuid-aaa-bbb-ccc",
                "session_id": "sess_abc123",
                "interrupt_type": "product_selection",
                "payload": {"selected_product_id": "PROD001"},
            }
        }


class MarketingResponse(BaseModel):
    """마케팅 에이전트 응답"""
    status: Literal["waiting_for_user", "completed", "failed"]
    interrupt_type: Optional[str] = None  # waiting_for_user 시 어떤 interrupt인지
    thread_id: str
    session_id: str
    conversation_id: Optional[str] = None
    recommended_products: Optional[List[Dict[str, Any]]] = None
    persona_info: Optional[Dict[str, Any]] = None
    messages: Optional[List[Dict[str, Any]]] = None
    selected_product: Optional[Dict[str, Any]] = None
    regeneration_history: Optional[List[Dict[str, Any]]] = None
    logs: Optional[List[str]] = None
    error: Optional[str] = None


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/chat", response_model=MarketingResponse)
async def chat(
    request: ChatRequest,
    req: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    대화 처리 (신규 + 이어가기 통합)

    - thread_id 없음: 새 대화 시작
    - thread_id 있음: 기존 대화 이어가기
    - thread_id가 interrupt 대기 상태이면 waiting_for_user 반환 → /resume 사용 안내
    """
    try:
        agent = get_agent(req)
        result = await agent.chat(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=user_id,
            model=request.model,
            thread_id=request.thread_id,
        )

        # 신규 대화 시 Conversation 레코드 생성
        conv_id = request.conversation_id
        if not conv_id:
            conv_id = str(uuid.uuid4())
            db = SessionLocal()
            try:
                conv = Conversation(
                    id=conv_id,
                    user_id=user_id,
                    thread_id=result["thread_id"],
                    session_id=result["session_id"],
                    title="새 대화",
                )
                db.add(conv)
                db.commit()
            finally:
                db.close()

        result["conversation_id"] = conv_id

        logger.info(
            "chat_completed",
            status=result.get("status"),
            interrupt_type=result.get("interrupt_type"),
            thread_id=result.get("thread_id"),
            session_id=request.session_id,
            user_id=user_id,
            conversation_id=conv_id,
        )

        return MarketingResponse(**result)

    except Exception as e:
        logger.error("chat_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume", response_model=MarketingResponse)
async def resume_interrupt(
    request: ResumeRequest,
    req: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    Interrupt 재개 (모든 interrupt 타입 통합)

    /chat에서 status: "waiting_for_user"를 받은 후,
    interrupt_type에 맞는 payload를 담아 호출합니다.

    현재 지원:
        interrupt_type: "product_selection"
        payload: {"selected_product_id": "PROD001"}
    """
    try:
        agent = get_agent(req)
        result = await agent.resume_interrupt(
            thread_id=request.thread_id,
            interrupt_type=request.interrupt_type,
            payload=request.payload,
            session_id=request.session_id,
            user_id=user_id,
            model=request.model,
        )

        # 메시지 생성 완료 시 generated_messages 테이블에 저장
        api_messages = result.get("messages")
        logger.info(
            "resume_save_check",
            status=result.get("status"),
            messages_count=len(api_messages) if api_messages else 0,
            has_conv_id=bool(request.conversation_id),
        )
        if result.get("status") == "completed" and api_messages:
            msg = api_messages[0]
            conv_id = request.conversation_id

            # conversation_id 없으면 thread_id로 역조회
            if not conv_id:
                db = SessionLocal()
                try:
                    conv = db.query(Conversation).filter(
                        Conversation.thread_id == request.thread_id
                    ).first()
                    conv_id = conv.id if conv else None
                finally:
                    db.close()

            if conv_id:
                # content 폴백: message → content → 전체 JSON
                content = (
                    msg.get("message")
                    or msg.get("content")
                    or json.dumps(msg, ensure_ascii=False)
                )
                db = SessionLocal()
                try:
                    gm = GeneratedMessage(
                        conversation_id=conv_id,
                        user_id=user_id,
                        product_id=request.payload.get("selected_product_id", ""),
                        title=msg.get("title") or msg.get("headline"),
                        content=content,
                        thread_id=request.thread_id,
                    )
                    db.add(gm)
                    db.commit()
                    logger.info(
                        "generated_message_saved",
                        conversation_id=conv_id,
                        product_id=gm.product_id,
                        user_id=user_id,
                        content_length=len(content),
                    )
                except Exception as db_err:
                    logger.error(
                        "generated_message_save_failed",
                        error=str(db_err),
                        conv_id=conv_id,
                        product_id=request.payload.get("selected_product_id"),
                        exc_info=True,
                    )
                finally:
                    db.close()
            else:
                logger.warning("generated_message_skip_no_conv_id", thread_id=request.thread_id)

        logger.info(
            "resume_completed",
            status=result.get("status"),
            interrupt_type=request.interrupt_type,
            thread_id=request.thread_id,
            session_id=request.session_id,
            user_id=user_id,
        )

        return MarketingResponse(**result)

    except Exception as e:
        logger.error(
            "resume_failed",
            interrupt_type=request.interrupt_type,
            thread_id=request.thread_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Marketing API is running"}
