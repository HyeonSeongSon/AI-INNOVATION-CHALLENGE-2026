from .workflow import build_workflow
from .state import MarketingAssistantState
from ...core.logging import get_logger
from langchain_core.messages import HumanMessage, AIMessage
from typing import Optional, Dict, Any, List

_logger = get_logger("marketing_agent")

class MarketingAgent:
    def __init__(self, checkpointer=None):
        self.workflow = build_workflow(checkpointer=checkpointer)

    # ============================================================
    # 내부 헬퍼
    # ============================================================

    def _build_config(
        self,
        thread_id: str,
        session_id: str,
        user_id: str,
        model: Optional[str] = None,
    ) -> Dict:
        configurable = {
            "thread_id": thread_id,
            "session_id": session_id,
            "user_id": user_id,
        }
        if model:
            configurable["model"] = model
        return {"configurable": configurable}

    def _history_to_messages(self, history: list) -> List:
        """DB 메시지 목록 → LangChain 메시지 객체 변환

        history 항목은 {"role": "user"|"assistant", "content": str, ...} 형식.
        LLM 컨텍스트에는 role/content만 필요 — 나머지 메타데이터는 무시.
        """
        result = []
        for entry in history:
            role = entry.get("role")
            content = entry.get("content", "")
            if role == "user":
                result.append(HumanMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
        return result

    def _extract_response_messages(self, result: Dict) -> list:
        """
        crm_message_node 플로우: generated_tasks의 message content
        그 외: state messages에서 마지막 AIMessage
        """
        generated_tasks = result.get("generated_tasks", [])
        if generated_tasks:
            messages = []
            for t in generated_tasks:
                msg_data = t["message"]
                if isinstance(msg_data, dict):
                    title = msg_data.get("title", "")
                    content = msg_data.get("message", "")
                elif hasattr(msg_data, "content"):
                    title = ""
                    content = msg_data.content
                else:
                    title = ""
                    content = str(msg_data)
                messages.append({
                    "role": "assistant",
                    "product_id": t["product_id"],
                    "brand": t["brand"],
                    "purpose": t["purpose"],
                    "title": title,
                    "content": content,
                })
            return messages

        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                return [{"role": "assistant", "content": msg.content}]
        return []

    # ============================================================
    # Public API
    # ============================================================

    async def chat(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        conversation_id: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        대화 처리

        - thread_id = conversation_id 고정 (LangGraph checkpointer가 messages 보존)
        - init_node가 매 요청마다 task-scope 필드(generated_tasks 등)를 리셋
        - 현재 사용자 메시지만 initial_state에 포함 (이력은 checkpoint에서 자동 복원)

        Returns:
            {
                "status": "completed" | "failed",
                "thread_id": str,
                "session_id": str,
                "recommended_products": [...],
                "messages": [...],
                "logs": [...],
                "error": str | None
            }
        """
        thread_id = conversation_id  # 고정 — checkpointer가 대화 이력 관리
        config = self._build_config(thread_id, session_id, user_id, model)

        # 현재 메시지만 전달 — 이전 이력은 LangGraph checkpoint에서 자동 복원
        initial_state: MarketingAssistantState = {"messages": [HumanMessage(content=user_input)]}

        try:
            result = await self.workflow.ainvoke(initial_state, config)

            intermediate = result.get("intermediate", {})
            raw_status = result.get("status")
            api_status = "failed" if raw_status in ("failed", "quality_check_failed") else "completed"

            return {
                "status": api_status,
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": result.get("recommended_products", []),
                "messages": self._extract_response_messages(result),
                "generated_tasks": result.get("generated_tasks", []),
                "regeneration_history": intermediate.get("quality_check", {}).get("regeneration_history", []),
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
                "logs": [f"[ERROR] 대화 처리 실패: {str(e)}"],
                "error": str(e),
            }
