"""
Marketing Agent API 엔드포인트
Supervisor + CRM subgraph 기반
"""

import asyncio
import uuid
from datetime import datetime, timezone

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any
from ..config.settings import ALLOWED_MODEL_PREFIXES, settings
from ..core.auth import UserContext
from ..core.logging import get_logger
from ..core.database import SessionLocal
from ..core.models import Conversation, GeneratedMessage, ConversationMessage
from .deps import get_user_from_headers

logger = get_logger("marketing_api")

router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


def get_agent_v2(request: Request):
    return request.app.state.agent_v2


def get_chat_stream_semaphore(request: Request) -> "asyncio.Semaphore":
    return request.app.state.chat_stream_semaphore



# ============================================================
# 대화 이력 헬퍼
# ============================================================


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
        logger.warning("save_messages_best_effort_failed", error_type=type(e).__name__, conversation_id=conversation_id, exc_info=True)
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
        db.rollback()
        logger.error("create_conversation_failed", conv_id=conv_id, user_id=user_id, error_type=type(e).__name__)
        raise
    finally:
        db.close()


def _verify_conversation_ownership(conv_id: str, user_id: str, role: str = "user") -> None:
    """conversation_id 소유자 검증. 미존재 → 404, 타인 소유 → 403."""
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
        if role != "admin" and conv.user_id != user_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
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
        saved_items: list[GeneratedMessage] = []
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
            saved_items.append(gm)
        if saved_items:
            db.commit()
        for gm in saved_items:
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
            error_type=type(db_err).__name__,
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
    user_input: str = Field(max_length=50_000)
    session_id: str = Field(max_length=100)
    conversation_id: Optional[str] = None  # None이면 신규 대화 레코드 생성
    model: Optional[str] = None
    file_records: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=500)

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not any(v.startswith(p) for p in ALLOWED_MODEL_PREFIXES):
            raise ValueError(f"지원하지 않는 모델명: {v}")
        return v

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
    current_user: UserContext = Depends(get_user_from_headers),
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
        loop = asyncio.get_running_loop()
        db_executor = req.app.state.db_executor
        if not conv_id:
            conv_id = str(uuid.uuid4())
            await loop.run_in_executor(db_executor, _create_conversation, conv_id, user_id, request.session_id)
        else:
            # IDOR 방어: 클라이언트가 전달한 conversation_id가 현재 사용자 소유인지 검증
            await loop.run_in_executor(
                db_executor, _verify_conversation_ownership, conv_id, user_id, current_user.role
            )

        # 2. 에이전트 호출 — conversation_id 전달, history 제거
        result = await agent.chat(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=user_id,
            role=current_user.role,
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

        asyncio.create_task(asyncio.to_thread(_save_conversation_messages_best_effort, conv_id, new_entries))

        # 품질 검사 통과 메시지만 generated_messages 저장
        if status == "completed" and conv_id:
            generated_tasks = result.get("generated_tasks", [])
            asyncio.create_task(asyncio.to_thread(
                _save_generated_messages_best_effort,
                conv_id, user_id, generated_tasks,
                request.user_input, thread_id,
                result.get("regeneration_history"),
            ))

        logger.info(
            "chat_v2_completed",
            status=status,
            thread_id=thread_id,
            session_id=request.session_id,
            user_id=user_id,
            conversation_id=conv_id,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_v2_failed", error_type=type(e).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다.")


@router.post("/chat/v2/stream")
async def chat_v2_stream(
    request: ChatRequest,
    req: Request,
    current_user: UserContext = Depends(get_user_from_headers),
):
    """
    대화 처리 v2 — SSE 스트리밍 (astream_events 기반)
    /chat/v2와 동일한 비즈니스 로직, 결과를 SSE로 스트리밍.

    SSE event types: node_start, token, log, node_end, result, error, done
    Keepalive: ': keepalive' SSE comments (~25s 간격)
    """
    # ── conversation_id 사전 확보 (chat_v2와 동일) ─────────────────
    try:
        user_id = current_user.user_id
        agent = get_agent_v2(req)
        conv_id = request.conversation_id
        loop = asyncio.get_running_loop()
        db_executor = req.app.state.db_executor
        if not conv_id:
            conv_id = str(uuid.uuid4())
            await loop.run_in_executor(db_executor, _create_conversation, conv_id, user_id, request.session_id)
        else:
            await loop.run_in_executor(
                db_executor, _verify_conversation_ownership, conv_id, user_id, current_user.role
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_v2_stream_setup_failed", error_type=type(e).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다.")

    # Write-ahead: 유저 메시지를 AI 처리 시작 전에 즉시 저장
    asyncio.create_task(asyncio.to_thread(
        _save_conversation_messages_best_effort,
        conv_id,
        [{"role": "user", "content": request.user_input, "type": "text",
          "timestamp": datetime.now(timezone.utc).isoformat(), "thread_id": conv_id}],
    ))

    async def _persist_results(result_data: dict) -> None:
        """result SSE 데이터를 DB에 저장한다. 유저 메시지는 이미 선행 저장됨."""
        try:
            status = result_data.get("status")
            thread_id = result_data.get("thread_id", conv_id)
            now = datetime.now(timezone.utc).isoformat()

            new_entries = []
            if status == "completed":
                ai_messages = result_data.get("messages", [])
                content = ai_messages[0].get("content", "") if ai_messages else ""
                new_entries.append({
                    "role": "assistant", "content": content,
                    "type": "text", "timestamp": now, "thread_id": thread_id,
                })
            elif status == "failed":
                error_msg = result_data.get("error") or "메시지 품질 검사를 통과하지 못했습니다."
                new_entries.append({
                    "role": "assistant", "content": error_msg,
                    "type": "error", "timestamp": now, "thread_id": thread_id,
                })

            if new_entries:
                asyncio.create_task(asyncio.to_thread(_save_conversation_messages_best_effort, conv_id, new_entries))

            if status == "completed":
                asyncio.create_task(asyncio.to_thread(
                    _save_generated_messages_best_effort,
                    conv_id, user_id, result_data.get("generated_tasks", []),
                    request.user_input, thread_id, [],
                ))

            logger.info(
                "chat_v2_stream_completed",
                status=status, thread_id=thread_id,
                conv_id=conv_id, user_id=user_id,
            )
        except Exception as e:
            logger.warning(
                "chat_v2_stream_db_persist_failed",
                error_type=type(e).__name__, conv_id=conv_id,
            )

    async def generate():
        _result_data: dict | None = None
        _error_payload: dict | None = None

        semaphore = get_chat_stream_semaphore(req)
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=settings.chat_stream_admission_timeout)
        except asyncio.TimeoutError:
            logger.warning("chat_v2_stream_admission_timeout", conv_id=conv_id)
            yield 'data: {"type":"error","message":"현재 요청이 많아 대기 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."}\n\n'
            yield 'data: {"type":"done"}\n\n'
            return

        try:
            async for chunk in agent.chat_stream(
                user_input=request.user_input,
                session_id=request.session_id,
                user_id=user_id,
                conversation_id=conv_id,
                role=current_user.role,
                model=request.model,
                file_records=request.file_records,
            ):
                if chunk.startswith("data: "):
                    try:
                        payload = _json.loads(chunk[len("data: "):].strip())
                        if isinstance(payload, dict):
                            if payload.get("type") == "result":
                                _result_data = payload
                            elif payload.get("type") == "error":
                                _error_payload = payload
                            elif payload.get("type") == "done":
                                if _result_data is not None:
                                    # asyncio.shield: 클라이언트 연결 해제로 외부 태스크가 취소돼도
                                    # _persist_results 내부 Future는 독립적으로 실행 완료된다.
                                    try:
                                        await asyncio.shield(_persist_results(_result_data))
                                    except asyncio.CancelledError:
                                        logger.info("chat_v2_stream_disconnected_during_persist", conv_id=conv_id)
                                        return
                                    _result_data = None
                                elif _error_payload is not None:
                                    error_msg = _error_payload.get("message") or "처리 중 오류가 발생했습니다."
                                    asyncio.create_task(asyncio.to_thread(
                                        _save_conversation_messages_best_effort, conv_id,
                                        [{"role": "assistant", "content": error_msg, "type": "error",
                                          "timestamp": datetime.now(timezone.utc).isoformat(), "thread_id": conv_id}],
                                    ))
                                    _error_payload = None
                    except Exception:
                        pass
                yield chunk

        except asyncio.CancelledError:
            logger.info("chat_v2_stream_disconnected", conv_id=conv_id)
            return
        except Exception as e:
            logger.error("chat_v2_stream_generate_failed", error_type=type(e).__name__, exc_info=True)
            asyncio.create_task(asyncio.to_thread(
                _save_conversation_messages_best_effort, conv_id,
                [{"role": "assistant", "content": "스트리밍 중 오류가 발생했습니다.", "type": "error",
                  "timestamp": datetime.now(timezone.utc).isoformat(), "thread_id": conv_id}],
            ))
            yield 'data: {"type":"error","message":"스트리밍 중 오류가 발생했습니다."}\n\n'
            yield 'data: {"type":"done"}\n\n'
            return
        finally:
            semaphore.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Marketing API is running"}
