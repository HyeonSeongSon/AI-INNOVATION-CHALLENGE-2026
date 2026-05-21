"""
Marketing Agent API 엔드포인트
Supervisor + CRM subgraph 기반
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from ..core.auth import UserContext
from ..core.logging import get_logger
from ..core.database import SessionLocal
from ..core.models import Conversation, GeneratedMessage, ConversationMessage
from .deps import get_current_user

logger = get_logger("marketing_api")

router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


def get_agent_v2(request: Request):
    return request.app.state.agent_v2



# ============================================================
# 대화 이력 헬퍼
# ============================================================

_CONTEXT_LIMIT = 50  # LLM 컨텍스트용 최근 메시지 수


def _load_conversation_messages(conversation_id: Optional[str]) -> list:
    """conversation_messages 테이블에서 최근 N건을 시간순으로 반환."""
    if not conversation_id:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id.desc())
            .limit(_CONTEXT_LIMIT)
            .all()
        )
        return [row.message_data for row in reversed(rows)]
    except Exception as e:
        logger.warning("load_conversation_messages_failed", conversation_id=conversation_id, error=str(e))
        return []
    finally:
        db.close()


def _save_conversation_messages_best_effort(conversation_id: str, new_entries: list) -> None:
    """새 메시지를 conversation_messages 테이블에 INSERT한다. 실패해도 대화 흐름에 영향 없음."""
    if not new_entries:
        return
    db = SessionLocal()
    try:
        for entry in new_entries:
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                message_data=entry,
            ))
        db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).update({"last_active_at": datetime.now(timezone.utc)})
        db.commit()
    except Exception as e:
        logger.warning("save_messages_best_effort_failed", error=str(e), conversation_id=conversation_id, exc_info=True)
        db.rollback()
        # 의도적으로 raise하지 않음 — 대화 이력 저장은 부가 데이터
    finally:
        db.close()


def _create_conversation(conv_id: str, user_id: str, session_id: str) -> None:
    db = SessionLocal()
    try:
        conv = Conversation(
            id=conv_id,
            user_id=user_id,
            thread_id=conv_id,
            session_id=session_id,
            title="새 대화 (v2)",
        )
        db.add(conv)
        db.commit()
    except Exception as e:
        logger.error("create_conversation_failed", conv_id=conv_id, user_id=user_id, error=str(e))
        raise
    finally:
        db.close()


def _save_generated_messages_best_effort(
    conv_id: str,
    user_id: str,
    generated_tasks: list,
    user_input: str,
    thread_id: str,
    regeneration_history: list | None,
) -> None:
    """생성된 메시지를 DB에 저장한다. 실패해도 응답에 영향 없음."""
    db = SessionLocal()
    try:
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
            gm = GeneratedMessage(
                conversation_id=conv_id,
                user_id=user_id,
                product_id=task.get("product_id", ""),
                product_name=task.get("product_name"),
                brand=task.get("brand"),
                sub_tag=task.get("sub_tag"),
                purpose=task.get("purpose"),
                user_input=user_input,
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
                regeneration_count=len(regeneration_history or []),
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
        db.rollback()
        logger.warning(
            "save_generated_messages_best_effort_failed",
            error=str(db_err),
            conv_id=conv_id,
            exc_info=True,
        )
        # 의도적으로 raise하지 않음 — 생성 메시지 저장은 부가 데이터
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

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_input": "PERSONA_001로 설화수 크림 신상품 홍보 메시지 만들어줘",
            "session_id": "sess_abc123",
            "conversation_id": None,
            "model": "gpt-4o-mini"
        }
    })


# ============================================================
# 엔드포인트
# ============================================================


@router.post("/chat/v2")
async def chat_v2(
    request: ChatRequest,
    req: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """
    대화 처리 v2 (interrupt 없는 새 추천 방식)

    - thread_id = conversation_id 고정 (LangGraph checkpointer가 messages 보존)
    - Conversation 레코드를 에이전트 호출 전에 확보하여 thread_id 일관성 보장
    """
    try:
        user_id = current_user.user_id
        agent = get_agent_v2(req)

        # 1. conversation_id 사전 확보 (에이전트 호출 전에 thread_id를 결정해야 함)
        conv_id = request.conversation_id
        if not conv_id:
            conv_id = str(uuid.uuid4())
            await asyncio.to_thread(_create_conversation, conv_id, user_id, request.session_id)

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

        await asyncio.to_thread(_save_conversation_messages_best_effort, conv_id, new_entries)

        # 품질 검사 통과 메시지만 generated_messages 저장
        if status == "completed" and conv_id:
            generated_tasks = result.get("generated_tasks", [])
            await asyncio.to_thread(
                _save_generated_messages_best_effort,
                conv_id, user_id, generated_tasks,
                request.user_input, thread_id,
                result.get("regeneration_history"),
            )

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
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다.")


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Marketing API is running"}
