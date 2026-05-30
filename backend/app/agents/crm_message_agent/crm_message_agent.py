import json
import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator

from .workflow import build_workflow
from .state import CRMMessageAgentState
from ...core.logging import get_logger
from ...config.settings import settings
from langchain_core.messages import HumanMessage, AIMessage

_logger = get_logger("crm_message_agent")


def _extract_from_output(output: Any) -> Dict[str, Any]:
    """on_chain_end output에서 state 변경분 추출. Command.update 또는 plain dict 처리."""
    try:
        from langgraph.types import Command as LGCommand
        if isinstance(output, LGCommand):
            return output.update or {}
        if isinstance(output, dict):
            return output
    except Exception:
        pass
    return {}



def _get_node_streaming_text(
    node_name: str,
    output: Any,
    acc: Dict[str, Any],
) -> str:
    """각 노드 on_chain_end 시점에 text_chunk로 스트리밍할 텍스트를 반환. 없으면 빈 문자열.

    원칙: accStreamingText(누적)가 result.messages[0](최종 메시지)와 정확히 일치하는
    에이전트만 스트리밍한다. 불일치 시 done 이벤트 후 setPendingConv가 로딩 버블을
    교체할 때 시각적 충돌이 발생한다.
    """
    if node_name == "generate_message_agent":
        # result.messages[0] = "## 제목\n\n내용" — 정확히 일치
        tasks = acc.get("generated_tasks", [])
        if not tasks or acc.get("status") == "failed":
            return ""
        msg_data = tasks[0].get("message", {})
        if isinstance(msg_data, dict):
            title = msg_data.get("title", "")
            content = msg_data.get("message", "") or msg_data.get("content", "")
        else:
            title, content = "", str(msg_data)
        return (f"## {title}\n\n{content}" if title and content else content or title)

    if node_name == "supervisor":
        # generated_tasks가 있으면 generate_message_agent가 이미 최종 콘텐츠를 스트리밍했으므로 생략
        if acc.get("generated_tasks"):
            return ""
        # generated_tasks가 없을 때만 supervisor 응답이 result.messages[0]과 일치
        data = _extract_from_output(output)
        ai_msgs = [m for m in data.get("messages", []) if isinstance(m, AIMessage)]
        return ai_msgs[-1].content if ai_msgs else ""

    # search_agent: supervisor가 재가공 → result.messages[0]과 불일치 → 스트리밍 안 함
    # recommend_product_agent: 상품 카드 UI로 표시 → 텍스트 목록과 불일치 → 스트리밍 안 함
    return ""


_TRACKED_NODES: frozenset[str] = frozenset({
    "supervisor",
    "search_agent",
    "recommend_product_agent",
    "generate_message_agent",
    "data_registration_agent",
})


class CRMMessageAgent:
    def __init__(self, checkpointer=None):
        self.workflow = build_workflow(checkpointer=checkpointer)

    def _build_config(
        self,
        thread_id: str,
        session_id: str,
        user_id: str,
        role: str = "user",
        model: Optional[str] = None,
        services: Any = None,
    ) -> Dict:
        configurable = {
            "thread_id": thread_id,
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
        }
        if model:
            configurable["model"] = model
        if services is not None:
            configurable["services"] = services
        return {
            "configurable": configurable,
            "recursion_limit": settings.langgraph_recursion_limit,
        }

    def _extract_response_messages(self, result: Dict) -> list:
        """
        generated_tasks가 있으면 메시지 목록으로 변환,
        없으면 supervisor의 최종 AIMessage를 반환
        """
        generated_tasks = result.get("generated_tasks", [])
        if generated_tasks:
            messages = []
            for t in generated_tasks:
                msg_data = t.get("message") or {}
                if isinstance(msg_data, dict):
                    title = msg_data.get("title", "")
                    content = msg_data.get("message", "") or msg_data.get("content", "")
                elif hasattr(msg_data, "content"):
                    title = ""
                    content = msg_data.content
                else:
                    title = ""
                    content = str(msg_data)
                messages.append({
                    "role": "assistant",
                    "product_id": t.get("product_id"),
                    "brand": t.get("brand"),
                    "purpose": t.get("purpose"),
                    "title": title,
                    "content": content,
                })
            return messages

        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                return [{"role": "assistant", "content": msg.content}]
        return []

    async def chat(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        conversation_id: str,
        role: str = "user",
        model: Optional[str] = None,
        file_records: Optional[List[Dict[str, Any]]] = None,
        services: Any = None,
    ) -> Dict[str, Any]:
        """
        대화 처리

        - thread_id = conversation_id 고정 (LangGraph checkpointer가 messages 보존)
        - 현재 사용자 메시지만 initial_state에 포함 (이력은 checkpoint에서 자동 복원)
        - file_records 제공 시 supervisor가 data_registration_agent로 라우팅
        - generated_tasks, recommended_products는 state["intermediate"]에서 추출

        Returns:
            {
                "status": "completed" | "failed",
                "thread_id": str,
                "session_id": str,
                "recommended_products": [...],
                "generated_tasks": [...],
                "messages": [...],
                "regeneration_history": [],
                "logs": [...],
                "error": str | None
            }
        """
        thread_id = conversation_id
        config = self._build_config(thread_id, session_id, user_id, role, model, services)

        initial_state: CRMMessageAgentState = {
            "messages": [HumanMessage(content=user_input)],
            "recommended_products": [],  # 턴 시작 시 리셋 (_overwrite reducer가 체크포인트 값을 덮어씀)
            "generated_tasks": [],       # 턴 시작 시 리셋
            "task_plan": [],             # 턴 시작 시 리셋 (새 요청마다 LLM이 다시 플랜 결정)
            "status": None,              # 턴 시작 시 리셋 (이전 turn의 error 상태 승계 방지)
            "error": None,
            "error_details": None,
            **({"file_records": file_records} if file_records else {}),
        }

        try:
            result = await asyncio.wait_for(
                self.workflow.ainvoke(initial_state, config),
                timeout=settings.graph_execution_timeout,
            )
        except asyncio.TimeoutError:
            _logger.error("workflow_timeout", thread_id=thread_id)
            return {
                "status": "failed",
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": [],
                "messages": [],
                "generated_tasks": [],
                "regeneration_history": [],
                "logs": ["[ERROR] 처리 시간이 초과되었습니다."],
                "error": "처리 시간이 초과되었습니다.",
            }
        try:
            intermediate = result.get("intermediate", {})
            raw_status = result.get("status")
            api_status = "failed" if raw_status == "failed" else "completed"

            return {
                "status": api_status,
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": result.get("recommended_products", []),
                "messages": self._extract_response_messages(result),
                "generated_tasks": result.get("generated_tasks", []),
                "regeneration_history": [],
                "logs": result.get("logs", []),
                "error": result.get("error"),
            }

        except Exception as e:
            _logger.error("chat_failed", error_type=type(e).__name__, exc_info=True)
            return {
                "status": "failed",
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": [],
                "messages": [],
                "generated_tasks": [],
                "regeneration_history": [],
                "logs": ["[ERROR] 대화 처리 실패"],
            }

    async def chat_stream(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        conversation_id: str,
        role: str = "user",
        model: Optional[str] = None,
        file_records: Optional[List[Dict[str, Any]]] = None,
        services: Any = None,
    ) -> AsyncGenerator[str, None]:
        """
        astream_events(version="v2") 기반 SSE 스트리밍 generator.

        yields: 'data: {json}\n\n' 형식의 SSE 문자열, 또는 ': keepalive\n\n'
        DB 저장은 호출자(marketing_api)의 generate() 래퍼에서 처리.

        SSE event types:
          node_start — 노드 진입 (tracked nodes 기준, supervisor는 최초 1회만)
          token      — LLM 토큰 (supervisor 직접 호출분만; A2A 너머 토큰은 미전달)
          text_chunk — 생성 메시지 콘텐츠 청크 (generate_message_agent 완료 후 점진적 방출)
          text_done  — text_chunk 시퀀스 완료 신호 (커서 제거용)
          log        — state["logs"] 항목
          node_end   — 노드 완료
          result     — 최종 결과 (recommended_products, generated_tasks, messages 포함)
          error      — 고정 한국어 메시지 (str(e) 절대 포함 금지)
          done       — 스트림 종료 신호
        """
        thread_id = conversation_id
        config = self._build_config(thread_id, session_id, user_id, role, model, services)
        initial_state: CRMMessageAgentState = {
            "messages": [HumanMessage(content=user_input)],
            "recommended_products": [],
            "generated_tasks": [],
            "task_plan": [],
            "status": None,
            "error": None,
            "error_details": None,
            **({"file_records": file_records} if file_records else {}),
        }

        # DB 저장 및 result 이벤트용 state 누적
        _acc: Dict[str, Any] = {
            "logs": [], "status": None, "recommended_products": [],
            "generated_tasks": [], "messages": [], "error": None,
        }
        _started_nodes: set[str] = set()  # supervisor 다중 실행 시 node_start 중복 방지
        step = 0

        def _sse(data: Dict[str, Any]) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        def _accumulate(node_name: str, output: Any) -> None:
            data = _extract_from_output(output)
            if data.get("logs"):
                _acc["logs"].extend(data["logs"])           # add reducer
            if data.get("status") is not None:
                _acc["status"] = data["status"]             # _overwrite reducer
            if "recommended_products" in data:
                _acc["recommended_products"] = data["recommended_products"]
            if "generated_tasks" in data:
                _acc["generated_tasks"] = data["generated_tasks"]
            if data.get("error") is not None:
                _acc["error"] = data["error"]
            # supervisor 최종 패스(plain dict 반환)의 AIMessage만 캡처
            if node_name == "supervisor":
                ai_msgs = [m for m in data.get("messages", []) if isinstance(m, AIMessage)]
                if ai_msgs:
                    _acc["messages"] = ai_msgs

        # ── Producer: astream_events → queue ────────────────────────────
        queue: asyncio.Queue = asyncio.Queue()

        async def _produce() -> None:
            try:
                async for event in self.workflow.astream_events(
                    initial_state, config, version="v2"
                ):
                    await queue.put(("event", event))
                await queue.put(("done", None))
            except asyncio.CancelledError:
                await queue.put(("cancelled", None))
            except Exception as e:
                _logger.error(
                    "chat_stream_producer_failed",
                    error_type=type(e).__name__,
                    exc_info=True,
                )
                await queue.put(("error", None))  # str(e) 절대 큐에 넣지 않음

        producer = asyncio.create_task(_produce())
        _deadline = asyncio.get_event_loop().time() + settings.graph_execution_timeout
        try:
            while True:
                _remaining = _deadline - asyncio.get_event_loop().time()
                if _remaining <= 0:
                    yield _sse({"type": "error", "message": "처리 시간이 초과되었습니다."})
                    yield _sse({"type": "done"})
                    return
                try:
                    kind, data = await asyncio.wait_for(
                        queue.get(), timeout=min(settings.sse_keepalive_timeout, _remaining)
                    )
                except asyncio.TimeoutError:
                    if asyncio.get_event_loop().time() >= _deadline:
                        yield _sse({"type": "error", "message": "처리 시간이 초과되었습니다."})
                        yield _sse({"type": "done"})
                        return
                    yield ": keepalive\n\n"
                    continue

                if kind == "cancelled":
                    return  # 클라이언트 disconnect — yield 없이 종료
                if kind == "error":
                    yield _sse({"type": "error", "message": "처리 중 오류가 발생했습니다."})
                    yield _sse({"type": "done"})
                    return
                if kind == "done":
                    break

                # kind == "event"
                event = data
                event_type: str = event.get("event", "")
                node_name: str = (
                    event.get("metadata", {}).get("langgraph_node")
                    or event.get("name", "")
                )

                if event_type == "on_chain_start" and node_name in _TRACKED_NODES:
                    if node_name not in _started_nodes:  # supervisor 중복 방지
                        step += 1
                        _started_nodes.add(node_name)
                        yield _sse({"type": "node_start", "node": node_name, "step": step})

                elif event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is not None:
                        content = getattr(chunk, "content", "")
                        if content:
                            yield _sse({"type": "token", "content": content})

                elif event_type == "on_chain_end" and node_name in _TRACKED_NODES:
                    output = event.get("data", {}).get("output")
                    _accumulate(node_name, output)
                    log_data = _extract_from_output(output)
                    for log_line in log_data.get("logs", []):
                        yield _sse({"type": "log", "message": log_line})
                    streaming_text = _get_node_streaming_text(node_name, output, _acc)
                    if streaming_text:
                        chunk_size = 3
                        for i in range(0, len(streaming_text), chunk_size):
                            yield _sse({"type": "text_chunk", "content": streaming_text[i:i + chunk_size]})
                            await asyncio.sleep(0.015)
                        yield _sse({"type": "text_done"})
                    yield _sse({"type": "node_end", "node": node_name})

        except asyncio.CancelledError:
            _logger.info("chat_stream_cancelled", thread_id=thread_id)
            return
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

        # ── Result 이벤트 ────────────────────────────────────────────────
        api_status = "failed" if _acc["status"] == "failed" else "completed"
        response_messages = self._extract_response_messages({
            "generated_tasks": _acc["generated_tasks"],
            "messages": _acc["messages"],
        })
        yield _sse({
            "type": "result",
            "status": api_status,
            "thread_id": thread_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "recommended_products": _acc["recommended_products"],
            "generated_tasks": _acc["generated_tasks"],
            "messages": response_messages,
            "logs": _acc["logs"],
            "error": _acc["error"],
        })
        yield _sse({"type": "done"})
