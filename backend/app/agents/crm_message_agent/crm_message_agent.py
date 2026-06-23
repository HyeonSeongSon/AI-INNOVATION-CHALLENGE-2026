import json
import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator, Awaitable, Callable

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
        # SSE 데드라인 초과 후에도 백그라운드에서 계속 도는 워크플로우 완료 태스크 보관
        # (참조를 안 들고 있으면 asyncio가 아직 안 끝난 task를 GC해버릴 수 있음).
        # crm_server.py의 lifespan 종료 절차가 배포 시 이 task들을 기다려준다.
        self._background_tasks: set[asyncio.Task] = set()

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

    def _build_chat_result_payload(
        self,
        result: Dict[str, Any],
        thread_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        try:
            raw_status = result.get("status")
            api_status = "failed" if raw_status == "failed" else "completed"

            return {
                "status": api_status,
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": result.get("recommended_products", []),
                "messages": self._extract_response_messages(result),
                "generated_tasks": result.get("generated_tasks", []),
                "quality_failed_tasks": result.get("quality_failed_tasks", []),
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
                "quality_failed_tasks": [],
                "regeneration_history": [],
                "logs": ["[ERROR] 대화 처리 실패"],
            }

    def _detach_chat_to_background(
        self,
        task: asyncio.Task,
        thread_id: str,
        session_id: str,
        on_late_result: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        """데드라인 초과로 호출자에게는 이미 실패 응답을 보냈지만, 워크플로우는 취소하지
        않고 끝까지 진행시켜 결과를 늦게라도 저장한다(A2A 너머 recommend/generate는
        로컬 task 취소와 무관하게 계속 실행되므로, 취소해도 자원이 절약되지 않고
        결과만 버려짐)."""
        async def _continue() -> None:
            try:
                async with asyncio.timeout(settings.graph_execution_timeout):
                    result = await task
            except (TimeoutError, asyncio.CancelledError):
                _logger.warning("chat_late_completion_timeout", thread_id=thread_id)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return
            except Exception as e:
                _logger.error(
                    "chat_late_completion_failed",
                    error_type=type(e).__name__,
                    thread_id=thread_id,
                    exc_info=True,
                )
                return

            _logger.info("chat_late_completion", thread_id=thread_id)
            payload = self._build_chat_result_payload(result, thread_id, session_id)
            try:
                await on_late_result(payload)
            except Exception as e:
                _logger.warning(
                    "chat_late_result_callback_failed",
                    thread_id=thread_id,
                    error_type=type(e).__name__,
                )

        continuation = asyncio.create_task(_continue())
        for t in (task, continuation):
            self._background_tasks.add(t)
            t.add_done_callback(self._background_tasks.discard)

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
        on_late_result: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        대화 처리

        - thread_id = conversation_id 고정 (LangGraph checkpointer가 messages 보존)
        - 현재 사용자 메시지만 initial_state에 포함 (이력은 checkpoint에서 자동 복원)
        - file_records 제공 시 supervisor가 data_registration_agent로 라우팅
        - generated_tasks, recommended_products는 state["intermediate"]에서 추출

        on_late_result: 데드라인(graph_execution_timeout) 초과로 이미 실패 응답을
            반환한 뒤에도, 워크플로우가 실제로는 완료될 수 있다(A2A로 분리된
            recommend/generate 서비스는 로컬 task를 취소해도 멈추지 않음). 이 콜백이
            주어지면 데드라인 초과 시 워크플로우를 취소하지 않고 백그라운드에서 끝까지
            진행시켜, 완료되면 이 콜백에 result payload를 전달한다(예: DB에 늦게라도
            저장). 주어지지 않으면 기존과 동일하게 취소한다.

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
            "quality_failed_tasks": [],  # 턴 시작 시 리셋
            "task_plan": [],             # 턴 시작 시 리셋 (새 요청마다 LLM이 다시 플랜 결정)
            "status": None,              # 턴 시작 시 리셋 (이전 turn의 error 상태 승계 방지)
            "error": None,
            "error_details": None,
            **({"file_records": file_records} if file_records else {}),
        }

        task = asyncio.create_task(self.workflow.ainvoke(initial_state, config))
        done, _ = await asyncio.wait({task}, timeout=settings.graph_execution_timeout)
        if task not in done:
            _logger.error("workflow_timeout", thread_id=thread_id)
            if on_late_result is not None:
                self._detach_chat_to_background(task, thread_id, session_id, on_late_result)
            else:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            return {
                "status": "failed",
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": [],
                "messages": [],
                "generated_tasks": [],
                "quality_failed_tasks": [],
                "regeneration_history": [],
                "logs": ["[ERROR] 처리 시간이 초과되었습니다."],
                "error": "처리 시간이 초과되었습니다.",
            }

        try:
            result = task.result()
        except Exception as e:
            _logger.error("workflow_failed", error_type=type(e).__name__, thread_id=thread_id, exc_info=True)
            return {
                "status": "failed",
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": [],
                "messages": [],
                "generated_tasks": [],
                "quality_failed_tasks": [],
                "regeneration_history": [],
                "logs": ["[ERROR] 대화 처리 실패"],
            }

        return self._build_chat_result_payload(result, thread_id, session_id)

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
        on_late_result: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        release_semaphore: Optional[Callable[[], None]] = None,
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

        on_late_result: SSE 데드라인(graph_execution_timeout) 초과로 클라이언트에는
            이미 error/done을 보낸 뒤에도, 워크플로우가 실제로는 완료될 수 있다(A2A로
            분리된 recommend/generate 서비스는 로컬 task를 취소해도 멈추지 않음).
            이 콜백이 주어지면 데드라인 초과 시 워크플로우를 취소하지 않고 백그라운드에서
            끝까지 진행시켜, 완료되면 이 콜백에 result payload를 전달한다(예: DB에 늦게라도
            저장). 클라이언트에는 더 이상 전달할 수 없으므로 다음 대화 조회 시에만 노출된다.
        release_semaphore: 호출자가 동시성 게이팅용으로 들고 있는 세마포어의 release를
            넘겨준다. 실제 자원 사용이 끝나는 시점에 정확히 1회 호출된다 — 정상/즉시실패
            경로는 즉시, 데드라인 초과로 백그라운드에 detach된 경로는 백그라운드 작업이
            끝나는 시점에 호출된다. SSE 연결이 끝나는 시점이 아니라 실제 작업이 끝나는
            시점에 묶어야, 백그라운드로 넘어간 뒤에도 세마포어가 동시성 캡 역할을 유지한다.
        """
        thread_id = conversation_id
        config = self._build_config(thread_id, session_id, user_id, role, model, services)
        initial_state: CRMMessageAgentState = {
            "messages": [HumanMessage(content=user_input)],
            "recommended_products": [],
            "generated_tasks": [],
            "quality_failed_tasks": [],
            "task_plan": [],
            "status": None,
            "error": None,
            "error_details": None,
            **({"file_records": file_records} if file_records else {}),
        }

        # DB 저장 및 result 이벤트용 state 누적
        _acc: Dict[str, Any] = {
            "logs": [], "status": None, "recommended_products": [],
            "generated_tasks": [], "quality_failed_tasks": [], "messages": [], "error": None,
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
            if "quality_failed_tasks" in data:
                _acc["quality_failed_tasks"] = data["quality_failed_tasks"]
            if data.get("error") is not None:
                _acc["error"] = data["error"]
            # supervisor 최종 패스(plain dict 반환)의 AIMessage만 캡처
            if node_name == "supervisor":
                ai_msgs = [m for m in data.get("messages", []) if isinstance(m, AIMessage)]
                if ai_msgs:
                    _acc["messages"] = ai_msgs

        _semaphore_released = False

        def _release_semaphore_once() -> None:
            nonlocal _semaphore_released
            if release_semaphore is not None and not _semaphore_released:
                _semaphore_released = True
                release_semaphore()

        def _build_result_payload() -> Dict[str, Any]:
            api_status = "failed" if _acc["status"] == "failed" else "completed"
            return {
                "type": "result",
                "status": api_status,
                "thread_id": thread_id,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "recommended_products": _acc["recommended_products"],
                "generated_tasks": _acc["generated_tasks"],
                "quality_failed_tasks": _acc["quality_failed_tasks"],
                "messages": self._extract_response_messages({
                    "generated_tasks": _acc["generated_tasks"],
                    "messages": _acc["messages"],
                }),
                "logs": _acc["logs"],
                "error": _acc["error"],
            }

        async def _continue_in_background() -> None:
            """SSE 데드라인 초과로 클라이언트 스트림은 끝났지만, 워크플로우는 취소하지
            않고 끝까지 진행시켜 결과를 늦게라도 저장한다(A2A 너머 recommend/generate는
            로컬 task 취소와 무관하게 계속 실행되므로, 취소해도 자원이 절약되지 않고
            결과만 버려짐). 동시성 세마포어도 이 작업이 끝나는 시점에 release한다 —
            SSE 연결이 끝난 시점에 release하면, 백그라운드에서 자원을 계속 쓰는 동안
            세마포어가 빈 자리로 카운트되어 동시성 캡이 무력화된다."""
            try:
                try:
                    async with asyncio.timeout(settings.graph_execution_timeout):
                        while True:
                            kind, data = await queue.get()
                            if kind in ("cancelled", "error"):
                                return
                            if kind == "done":
                                break
                            event = data
                            if event.get("event") == "on_chain_end":
                                node_name = (
                                    event.get("metadata", {}).get("langgraph_node")
                                    or event.get("name", "")
                                )
                                if node_name in _TRACKED_NODES:
                                    _accumulate(node_name, event.get("data", {}).get("output"))
                except TimeoutError:
                    _logger.warning("chat_stream_late_completion_timeout", thread_id=thread_id)
                    producer.cancel()
                    await asyncio.gather(producer, return_exceptions=True)
                    return
                except asyncio.CancelledError:
                    producer.cancel()
                    await asyncio.gather(producer, return_exceptions=True)
                    return

                _logger.info("chat_stream_late_completion", thread_id=thread_id)
                if on_late_result is not None:
                    try:
                        await on_late_result(_build_result_payload())
                    except Exception as e:
                        _logger.warning(
                            "chat_stream_late_result_callback_failed",
                            thread_id=thread_id,
                            error_type=type(e).__name__,
                        )
            finally:
                _release_semaphore_once()

        _detached = False

        def _detach_to_background() -> None:
            """데드라인 초과 시 producer를 취소하지 않고 백그라운드로 넘긴다.

            producer와 continuation task 둘 다 self._background_tasks에 강한 참조를
            유지해야 한다 — chat_stream의 제너레이터 프레임이 정리되면 로컬 변수
            producer에 대한 참조가 사라져, 참조를 안 들고 있으면 asyncio가 아직 끝나지
            않은 task를 GC해버릴 수 있다."""
            nonlocal _detached
            if on_late_result is None and release_semaphore is None:
                return
            continuation = asyncio.create_task(_continue_in_background())
            for task in (producer, continuation):
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            _detached = True

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
        _loop = asyncio.get_running_loop()
        _deadline = _loop.time() + settings.graph_execution_timeout
        try:
            while True:
                _remaining = _deadline - _loop.time()
                if _remaining <= 0:
                    # 데드라인은 지났지만, 워크플로우가 그 직전에 끝나 큐에 결과가 이미
                    # 도착해 있을 수 있다(컨슈머가 토큰 스트리밍 sleep 등으로 잠시 지연된
                    # 사이 producer가 먼저 끝난 경우) — 버리기 전에 한 번 non-blocking으로
                    # 확인한다.
                    try:
                        kind, data = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        _detach_to_background()
                        if not _detached:
                            _release_semaphore_once()
                        yield _sse({"type": "error", "message": "처리 시간이 초과되었습니다."})
                        yield _sse({"type": "done"})
                        return
                else:
                    try:
                        kind, data = await asyncio.wait_for(
                            queue.get(), timeout=min(settings.sse_keepalive_timeout, _remaining)
                        )
                    except asyncio.TimeoutError:
                        if _loop.time() >= _deadline:
                            _detach_to_background()
                            if not _detached:
                                _release_semaphore_once()
                            yield _sse({"type": "error", "message": "처리 시간이 초과되었습니다."})
                            yield _sse({"type": "done"})
                            return
                        yield ": keepalive\n\n"
                        continue

                if kind == "cancelled":
                    _release_semaphore_once()
                    return  # 클라이언트 disconnect — yield 없이 종료
                if kind == "error":
                    _release_semaphore_once()
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
            _release_semaphore_once()
            return
        finally:
            if not _detached:
                producer.cancel()
                await asyncio.gather(producer, return_exceptions=True)

        # ── Result 이벤트 ────────────────────────────────────────────────
        _release_semaphore_once()
        yield _sse(_build_result_payload())
        yield _sse({"type": "done"})
