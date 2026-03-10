from .workflow import build_marketing_workflow
from .state import SupervisorState
from ...core.logging import get_logger
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from typing import Optional, Dict, Any, List
import uuid

_logger = get_logger("marketing_agent")

# 현재 지원하는 interrupt 타입 목록
INTERRUPT_TYPES = {
    "product_selection",
    # "content_approval",  # 미래 확장 예시
}


class MarketingAgent:
    def __init__(self, checkpointer=None):
        self.workflow = build_marketing_workflow(checkpointer=checkpointer)

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
                "status": "waiting_for_user" | "completed" | "failed",
                "interrupt_type": str | None,
                "thread_id": str,
                "session_id": str,
                "recommended_products": [...],
                "persona_info": {...},
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
        initial_state: SupervisorState = {"messages": seed_messages}

        try:
            result = await self.workflow.ainvoke(initial_state, config)

            # interrupt 감지 (CRM 상품 선택 대기)
            interrupts = result.get("__interrupt__", [])
            if interrupts:
                # ainvoke 반환값(result)은 부모 graph state라 서브그래프 intermediate가 없음.
                # wait_for_product_selection_node가 interrupt()에 담아 전달한 value에서 직접 읽음.
                interrupt_value = interrupts[0].value if interrupts else {}
                recommended_products = interrupt_value.get("recommended_products", [])
                persona_info = interrupt_value.get("persona_info")

                product_names = [p.get("product_name", "") for p in recommended_products]
                interrupt_msg = (
                    f"총 {len(product_names)}개 상품을 추천드렸습니다. "
                    f"{', '.join(product_names)} 중 상품 하나를 선택해주세요."
                )

                return {
                    "status": "waiting_for_user",
                    "interrupt_type": "product_selection",
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "recommended_products": recommended_products,
                    "persona_info": persona_info,
                    "messages": [{"role": "assistant", "content": interrupt_msg}],
                    "logs": result.get("logs", []),
                    "error": None,
                }

            # 정상 완료
            # fresh thread이므로 intermediate는 항상 현재 task 결과만 담고 있음
            intermediate = result.get("intermediate", {})
            raw_status = result.get("status")
            api_status = "failed" if raw_status in ("failed", "quality_check_failed") else "completed"

            return {
                "status": api_status,
                "interrupt_type": None,
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": intermediate.get("recommendation", {}).get("recommended_products", []),
                "persona_info": intermediate.get("recommendation", {}).get("persona_info"),
                "messages": self._extract_response_messages(result),
                "regeneration_history": intermediate.get("quality_check", {}).get("regeneration_history", []),
                "logs": result.get("logs", []),
                "error": result.get("error"),
            }

        except Exception as e:
            _logger.error("chat_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "interrupt_type": None,
                "thread_id": thread_id,
                "session_id": session_id,
                "recommended_products": [],
                "persona_info": None,
                "messages": [],
                "logs": [f"[ERROR] 대화 처리 실패: {str(e)}"],
                "error": str(e),
            }

    async def resume_interrupt(
        self,
        thread_id: str,
        interrupt_type: str,
        payload: Dict[str, Any],
        session_id: str,
        user_id: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Interrupt 재개 (모든 interrupt 타입 통합 처리)

        interrupt_type으로 내부 핸들러를 분기합니다.
        새 interrupt 타입 추가 시 elif 분기 + _resume_xxx() 메서드만 추가하면 됩니다.

        Args:
            interrupt_type: "product_selection" | 미래 타입들
            payload: interrupt 타입별 데이터
                     product_selection → {"selected_product_id": "PROD001"}
        """
        if interrupt_type not in INTERRUPT_TYPES:
            return {
                "status": "failed",
                "interrupt_type": interrupt_type,
                "thread_id": thread_id,
                "session_id": session_id,
                "messages": [],
                "selected_product": None,
                "recommended_products": [],
                "persona_info": None,
                "regeneration_history": [],
                "logs": [],
                "error": f"지원하지 않는 interrupt 타입: {interrupt_type}. 지원 타입: {INTERRUPT_TYPES}",
            }

        config = self._build_config(thread_id, session_id, user_id, model)

        if interrupt_type == "product_selection":
            selected_product_id = payload.get("selected_product_id")
            if not selected_product_id:
                return {
                    "status": "failed",
                    "interrupt_type": interrupt_type,
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "messages": [],
                    "selected_product": None,
                    "recommended_products": [],
                    "persona_info": None,
                    "regeneration_history": [],
                    "logs": [],
                    "error": "payload에 selected_product_id가 필요합니다.",
                }
            return await self._resume_product_selection(
                config, thread_id, session_id, selected_product_id
            )

    async def _resume_product_selection(
        self,
        config: Dict,
        thread_id: str,
        session_id: str,
        selected_product_id: str,
    ) -> Dict[str, Any]:
        """상품 선택 interrupt 재개"""
        try:
            current_state = await self.workflow.aget_state(config)

            _logger.info(
                "resume_product_selection",
                thread_id=thread_id,
                selected_product_id=selected_product_id,
                next_nodes=list(current_state.next) if current_state else [],
                tasks=[str(t) for t in current_state.tasks] if current_state else [],
            )

            recommended = (
                current_state.values.get("intermediate", {})
                .get("recommendation", {})
                .get("recommended_products", [])
            )
            selected = next(
                (p for p in recommended if p.get("product_id") == selected_product_id),
                {}
            )

            result = await self.workflow.ainvoke(
                Command(resume=selected_product_id),
                config
            )
            # 대화 이력은 DB(conversations.messages)가 source of truth.
            # LangGraph checkpoint에 역으로 메시지를 추가하지 않음.

            intermediate = result.get("intermediate", {})
            raw_status = result.get("status")
            api_status = "failed" if raw_status in ("failed", "quality_check_failed") else "completed"
            return {
                "status": api_status,
                "interrupt_type": None,
                "thread_id": thread_id,
                "session_id": session_id,
                "messages": intermediate.get("message", {}).get("messages", []),
                "selected_product": selected or None,
                "recommended_products": intermediate.get("recommendation", {}).get("recommended_products", []),
                "persona_info": intermediate.get("recommendation", {}).get("persona_info"),
                "regeneration_history": intermediate.get("quality_check", {}).get("regeneration_history", []),
                "logs": result.get("logs", []),
                "error": result.get("error"),
            }

        except Exception as e:
            _logger.error("resume_product_selection_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "interrupt_type": "product_selection",
                "thread_id": thread_id,
                "session_id": session_id,
                "messages": [],
                "selected_product": None,
                "recommended_products": [],
                "persona_info": None,
                "regeneration_history": [],
                "logs": [f"[ERROR] 상품 선택 재개 실패: {str(e)}"],
                "error": str(e),
            }
