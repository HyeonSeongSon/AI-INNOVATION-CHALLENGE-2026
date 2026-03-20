from .workflow import build_workflow
from .state import MarketingAssistantState
from ...core.logging import get_logger
from langchain_core.messages import HumanMessage, AIMessage
from typing import Optional, Dict, Any, List
import uuid

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
        CRM 플로우: intermediate["message"]["messages"]
        search_node 플로우: LangGraph messages에서 name=="search_node"인 마지막 AIMessage
        """
        intermediate = result.get("intermediate", {})
        crm_messages = intermediate.get("message", {}).get("messages", [])
        if crm_messages:
            return crm_messages

        for msg in reversed(result.get("messages", [])):
            if getattr(msg, "name", None) == "search_node":
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
        history: list,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        대화 처리

        - 매 호출마다 fresh thread_id 생성 (task 격리)
        - history: API 레이어가 DB에서 로드해 넘겨주는 이전 대화 이력
          ({"role": "user"|"assistant", "content": str, ...} 목록)
        - LangGraph 상태는 task마다 항상 깨끗하게 시작
          (intermediate, step, logs, status 등 stale 데이터 없음)

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
        thread_id = str(uuid.uuid4())  # 항상 fresh — task 격리의 핵심
        config = self._build_config(thread_id, session_id, user_id, model)

        # 이전 대화 이력 + 현재 사용자 메시지로 초기 상태 구성
        seed_messages = self._history_to_messages(history)
        seed_messages.append(HumanMessage(content=user_input))
        initial_state: MarketingAssistantState = {"messages": seed_messages}

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
