from .workflow import build_workflow
from .state import CRMMessageAgentState
from ...core.logging import get_logger
from langchain_core.messages import HumanMessage, AIMessage
from typing import Optional, Dict, Any, List

_logger = get_logger("crm_message_agent")


class CRMMessageAgent:
    def __init__(self, checkpointer=None):
        self.workflow = build_workflow(checkpointer=checkpointer)

    def _build_config(
        self,
        thread_id: str,
        session_id: str,
        user_id: str,
        model: Optional[str] = None,
        services: Any = None,
    ) -> Dict:
        configurable = {
            "thread_id": thread_id,
            "session_id": session_id,
            "user_id": user_id,
        }
        if model:
            configurable["model"] = model
        if services is not None:
            configurable["services"] = services
        return {"configurable": configurable}

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
        config = self._build_config(thread_id, session_id, user_id, model, services)

        initial_state: CRMMessageAgentState = {
            "messages": [HumanMessage(content=user_input)],
            "recommended_products": [],  # 턴 시작 시 리셋 (_overwrite reducer가 체크포인트 값을 덮어씀)
            "generated_tasks": [],       # 턴 시작 시 리셋
            "task_plan": [],             # 턴 시작 시 리셋 (새 요청마다 LLM이 다시 플랜 결정)
            **({"file_records": file_records} if file_records else {}),
        }

        try:
            result = await self.workflow.ainvoke(initial_state, config)

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
            _logger.error("chat_failed", error=str(e), exc_info=True)
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
