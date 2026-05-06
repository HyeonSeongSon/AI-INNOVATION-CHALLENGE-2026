"""
Marketing Agent API 엔드포인트
Supervisor + CRM subgraph 기반
"""

import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any
from sqlalchemy.orm.attributes import flag_modified

from ..agents.supervisor.marketing_agent import MarketingAgent
from ..agents.marketing_assistant.marketing_assistant_agent import MarketingAgent as MarketingAssistantAgent
from ..core.logging import get_logger
from ..core.database import SessionLocal
from ..core.models import Conversation, GeneratedMessage

logger = get_logger("marketing_api")

router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


def get_agent(request: Request) -> MarketingAgent:
    return request.app.state.agent


def get_agent_v2(request: Request) -> MarketingAssistantAgent:
    return request.app.state.agent_v2


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
# 대화 이력 헬퍼
# ============================================================

def _load_conversation_messages(conversation_id: Optional[str]) -> list:
    """conversations.messages JSON에서 대화 이력 로드.

    반환값: [{"role": "user"|"assistant", "content": str, ...}, ...] 목록
    conversation_id가 없거나 대화를 찾을 수 없으면 빈 리스트 반환.
    """
    if not conversation_id:
        return []
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        return list(conv.messages or []) if conv else []
    finally:
        db.close()


def _save_conversation_messages(conversation_id: str, new_entries: list) -> None:
    """conversations.messages JSON에 새 항목 추가 저장.

    SQLAlchemy는 JSON 필드의 in-place 변경을 감지하지 못하므로
    전체 리스트를 재할당 + flag_modified로 명시적 변경 표시.
    """
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            logger.warning("save_messages_no_conv", conversation_id=conversation_id)
            return
        current = list(conv.messages or [])
        current.extend(new_entries)
        conv.messages = current
        flag_modified(conv, "messages")
        conv.last_active_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.error("save_messages_failed", error=str(e), conversation_id=conversation_id)
        db.rollback()
    finally:
        db.close()


# ============================================================
# 데이터 모델
# ============================================================

class ChatRequest(BaseModel):
    """대화 요청 (신규 + 이어가기 통합)

    thread_id 제거: 클라이언트는 conversation_id로 대화 연속성을 관리합니다.
    thread_id는 매 /chat 호출마다 에이전트 내부에서 fresh UUID로 생성됩니다.
    interrupt/resume 시에는 /chat 응답의 thread_id를 /resume 요청에 그대로 사용하세요.
    """
    user_input: str
    session_id: str
    conversation_id: Optional[str] = None  # None이면 신규 대화 레코드 생성
    model: Optional[str] = None
    file_records: Optional[List[Dict[str, Any]]] = None  # 파일 업로드 시 파싱된 레코드 배열

    class Config:
        schema_extra = {
            "example": {
                "user_input": "PERSONA_001로 설화수 크림 신상품 홍보 메시지 만들어줘",
                "session_id": "sess_abc123",
                "conversation_id": None,
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

    - conversation_id 없음: 새 대화 시작 (새 Conversation 레코드 생성)
    - conversation_id 있음: 기존 대화 이어가기 (이력 로드 후 컨텍스트 전달)
    - 매 호출마다 fresh thread_id로 task 격리 → stale 상태 오염 없음
    - interrupt 발생 시 반환된 thread_id를 /resume에 사용
    """
    try:
        agent = get_agent(req)

        # 1. DB에서 이전 대화 이력 로드 (신규면 빈 리스트)
        history = _load_conversation_messages(request.conversation_id)

        # 2. 에이전트 호출 — thread_id는 에이전트 내부에서 fresh UUID 생성
        result = await agent.chat(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=user_id,
            history=history,
            model=request.model,
        )

        # 3. Conversation 레코드 생성 또는 thread_id 업데이트
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
                    messages=[],
                )
                db.add(conv)
                db.commit()
            finally:
                db.close()
        else:
            # 최신 task thread_id로 업데이트 (LangSmith 추적 / interrupt 복구용)
            db = SessionLocal()
            try:
                conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    conv.thread_id = result["thread_id"]
                    db.commit()
            finally:
                db.close()

        result["conversation_id"] = conv_id

        # 4. 대화 이력 DB 저장
        thread_id = result["thread_id"]
        now = datetime.now(timezone.utc).isoformat()
        status = result.get("status")

        new_entries = [
            {
                "role": "user",
                "content": request.user_input,
                "type": "text",
                "timestamp": now,
                "thread_id": thread_id,
            }
        ]

        if status == "waiting_for_user":
            # interrupt 메시지 저장 — thread_id 포함해 /resume 복구 가능하게
            interrupt_content = (
                result["messages"][0]["content"] if result.get("messages") else ""
            )
            new_entries.append({
                "role": "assistant",
                "content": interrupt_content,
                "type": "product_selection_prompt",
                "timestamp": now,
                "thread_id": thread_id,
                "recommended_products": result.get("recommended_products", []),
                "persona_info": result.get("persona_info"),
            })
        elif status == "completed":
            ai_messages = result.get("messages", [])
            content = ai_messages[0].get("content", "") if ai_messages else ""
            new_entries.append({
                "role": "assistant",
                "content": content,
                "type": "text",
                "timestamp": now,
                "thread_id": thread_id,
            })
        # status == "failed": user 항목만 저장, assistant 항목 없음 (이력 오염 방지)

        _save_conversation_messages(conv_id, new_entries)

        logger.info(
            "chat_completed",
            status=status,
            interrupt_type=result.get("interrupt_type"),
            thread_id=thread_id,
            session_id=request.session_id,
            user_id=user_id,
            conversation_id=conv_id,
        )

        return MarketingResponse(**result)

    except Exception as e:
        logger.error("chat_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/v2")
async def chat_v2(
    request: ChatRequest,
    req: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    대화 처리 v2 (interrupt 없는 새 추천 방식)

    - thread_id = conversation_id 고정 (LangGraph checkpointer가 messages 보존)
    - Conversation 레코드를 에이전트 호출 전에 확보하여 thread_id 일관성 보장
    """
    try:
        agent = get_agent_v2(req)

        # 1. conversation_id 사전 확보 (에이전트 호출 전에 thread_id를 결정해야 함)
        conv_id = request.conversation_id
        if not conv_id:
            conv_id = str(uuid.uuid4())
            db = SessionLocal()
            try:
                conv = Conversation(
                    id=conv_id,
                    user_id=user_id,
                    thread_id=conv_id,   # thread_id = id 고정
                    session_id=request.session_id,
                    title="새 대화 (v2)",
                    messages=[],
                )
                db.add(conv)
                db.commit()
            finally:
                db.close()

        # 2. 에이전트 호출 — conversation_id 전달, history 제거
        result = await agent.chat(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=user_id,
            conversation_id=conv_id,
            model=request.model,
            file_records=request.file_records,
        )

        result["conversation_id"] = conv_id

        thread_id = result["thread_id"]
        now = datetime.now(timezone.utc).isoformat()
        status = result.get("status")

        new_entries = [
            {
                "role": "user",
                "content": request.user_input,
                "type": "text",
                "timestamp": now,
                "thread_id": thread_id,
            }
        ]

        if status == "completed":
            ai_messages = result.get("messages", [])
            content = ai_messages[0].get("content", "") if ai_messages else ""
            new_entries.append({
                "role": "assistant",
                "content": content,
                "type": "text",
                "timestamp": now,
                "thread_id": thread_id,
            })
        elif status == "failed":
            error_msg = result.get("error") or "메시지 품질 검사를 통과하지 못했습니다. 내용을 조정하여 다시 시도해주세요."
            new_entries.append({
                "role": "assistant",
                "content": error_msg,
                "type": "error",
                "timestamp": now,
                "thread_id": thread_id,
            })

        _save_conversation_messages(conv_id, new_entries)

        # 품질 검사 통과 메시지만 generated_messages 저장
        if status == "completed" and conv_id:
            generated_tasks = result.get("generated_tasks", [])
            for task in generated_tasks:
                _quality = task.get("quality_check") or {}
                _scores = _quality.get("llm_judge_scores") or {}
                msg = task.get("message") or {}
                content = msg.get("message") or msg.get("content", "")
                if not content:
                    continue
                if not _quality.get("passed"):
                    logger.info(
                        "generated_message_skip_quality_failed",
                        product_id=task.get("product_id"),
                        failed_stage=_quality.get("failed_stage"),
                    )
                    continue
                db = SessionLocal()
                try:
                    gm = GeneratedMessage(
                        conversation_id=conv_id,
                        user_id=user_id,
                        product_id=task.get("product_id", ""),
                        product_name=task.get("product_name"),
                        brand=task.get("brand"),
                        sub_tag=task.get("sub_tag"),
                        purpose=task.get("purpose"),
                        user_input=request.user_input,
                        title=msg.get("title"),
                        content=content,
                        quality_passed=_quality.get("passed"),
                        quality_failed_stage=_quality.get("failed_stage"),
                        quality_failure_reason=_quality.get("failure_reason"),
                        llm_score_accuracy=_scores.get("accuracy"),
                        llm_score_tone=_scores.get("tone"),
                        llm_score_personalization=_scores.get("personalization"),
                        llm_score_naturalness=_scores.get("naturalness"),
                        llm_score_cta_clarity=_scores.get("cta_clarity"),
                        llm_score_overall=_scores.get("overall"),
                        llm_feedback=_scores.get("feedback"),
                        quality_details={
                            "rule_check_passed": _quality.get("rule_check_passed"),
                            "rule_check_issues": _quality.get("rule_check_issues", []),
                            "semantic_check_passed": _quality.get("semantic_check_passed"),
                            "semantic_check_results": _quality.get("semantic_check_results", []),
                        },
                        regeneration_count=len(result.get("regeneration_history") or []),
                        thread_id=thread_id,
                    )
                    db.add(gm)
                    db.commit()
                    logger.info(
                        "generated_message_saved",
                        conversation_id=conv_id,
                        product_id=gm.product_id,
                        user_id=user_id,
                        quality_passed=gm.quality_passed,
                        llm_score_overall=float(gm.llm_score_overall) if gm.llm_score_overall else None,
                    )
                except Exception as db_err:
                    logger.error(
                        "generated_message_save_failed",
                        error=str(db_err),
                        conv_id=conv_id,
                        product_id=task.get("product_id"),
                        exc_info=True,
                    )
                finally:
                    db.close()

        logger.info(
            "chat_v2_completed",
            status=status,
            thread_id=thread_id,
            session_id=request.session_id,
            user_id=user_id,
            conversation_id=conv_id,
        )

        return result

    except Exception as e:
        logger.error("chat_v2_failed", error=str(e), exc_info=True)
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

        # conversation_id 확보 (없으면 thread_id로 역조회)
        conv_id = request.conversation_id
        if not conv_id:
            db = SessionLocal()
            try:
                conv = db.query(Conversation).filter(
                    Conversation.thread_id == request.thread_id
                ).first()
                conv_id = conv.id if conv else None
            finally:
                db.close()

        result["conversation_id"] = conv_id

        # 메시지 생성 완료 시 generated_messages 테이블에 저장
        api_messages = result.get("messages")
        logger.info(
            "resume_save_check",
            status=result.get("status"),
            messages_count=len(api_messages) if api_messages else 0,
            has_conv_id=bool(conv_id),
        )
        if result.get("status") == "completed" and api_messages and conv_id:
            msg = api_messages[0]
            content = (
                msg.get("message")
                or msg.get("content")
                or json.dumps(msg, ensure_ascii=False)
            )
            db = SessionLocal()
            try:
                _persona_info = result.get("persona_info") or {}
                _selected_product = result.get("selected_product") or {}
                _quality = result.get("quality_result") or {}
                _scores = _quality.get("llm_judge_scores") or {}
                gm = GeneratedMessage(
                    conversation_id=conv_id,
                    user_id=user_id,
                    product_id=request.payload.get("selected_product_id", ""),
                    product_name=_selected_product.get("product_name"),
                    brand=_selected_product.get("brand"),
                    sub_tag=_selected_product.get("sub_tag"),
                    purpose=result.get("purpose"),
                    user_input=result.get("user_input"),
                    title=msg.get("title") or msg.get("headline"),
                    content=content,
                    quality_passed=_quality.get("passed"),
                    quality_failed_stage=_quality.get("failed_stage"),
                    quality_failure_reason=_quality.get("failure_reason"),
                    llm_score_accuracy=_scores.get("accuracy"),
                    llm_score_tone=_scores.get("tone"),
                    llm_score_personalization=_scores.get("personalization"),
                    llm_score_naturalness=_scores.get("naturalness"),
                    llm_score_cta_clarity=_scores.get("cta_clarity"),
                    llm_score_overall=_scores.get("overall"),
                    llm_feedback=_scores.get("feedback"),
                    quality_details={
                        "rule_check_passed": _quality.get("rule_check_passed"),
                        "rule_check_issues": _quality.get("rule_check_issues", []),
                        "semantic_check_passed": _quality.get("semantic_check_passed"),
                        "groundedness_passed": _quality.get("groundedness_passed"),
                        "groundedness_result": _quality.get("groundedness_result"),
                    },
                    regeneration_count=result.get("regeneration_count", 0),
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
                    quality_passed=gm.quality_passed,
                    llm_score_overall=float(gm.llm_score_overall) if gm.llm_score_overall else None,
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
        elif not conv_id:
            logger.warning("generated_message_skip_no_conv_id", thread_id=request.thread_id)

        # 대화 이력 저장 (resume turn)
        if conv_id:
            now = datetime.now(timezone.utc).isoformat()
            selected_product = result.get("selected_product") or {}
            product_name = selected_product.get(
                "product_name", request.payload.get("selected_product_id", "")
            )
            new_entries = [
                {
                    "role": "user",
                    "content": f"{product_name}을(를) 선택하겠습니다.",
                    "type": "text",
                    "timestamp": now,
                    "thread_id": request.thread_id,
                }
            ]
            if result.get("status") == "completed" and api_messages:
                new_entries.append({
                    "role": "assistant",
                    "content": f"CRM 메시지 생성이 완료되었습니다: {api_messages[0].get('title', '')}",
                    "type": "crm_message",
                    "timestamp": now,
                    "thread_id": request.thread_id,
                    "crm_messages": api_messages,
                    "selected_product": selected_product,
                    "regeneration_history": result.get("regeneration_history", []),
                })
            _save_conversation_messages(conv_id, new_entries)

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
