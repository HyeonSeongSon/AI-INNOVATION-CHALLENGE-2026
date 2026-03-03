from .workflow import build_marketing_workflow
from .state import SupervisorState
from ...core.logging import get_logger
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from typing import Optional, Dict, Any
import uuid

_logger = get_logger("marketing_agent")

# 현재 지원하는 interrupt 타입 목록
INTERRUPT_TYPES = {
    "product_selection",
    # "content_approval",  # 미래 확장 예시
}


class MarketingAgent:
    def __init__(self):
        self.workflow = build_marketing_workflow()

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
        thread_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        대화 처리 (신규 + 이어가기 통합)

        - thread_id 없음: 새 대화 시작 (새 thread_id 생성)
        - thread_id 있음: 기존 대화 이어가기 (add_messages reducer가 메시지 누적)
        - thread_id가 interrupt 대기 상태이면 waiting_for_user 반환 → /resume 유도

        Returns:
            {
                "status": "waiting_for_user" | "completed" | "failed",
                "interrupt_type": str | None,    # waiting_for_user 시 어떤 interrupt인지
                "thread_id": str,
                "session_id": str,
                "recommended_products": [...],   # product_selection interrupt 시
                "persona_info": {...},            # product_selection interrupt 시
                "messages": [...],               # 완료 시
                "logs": [...],
                "error": str | None
            }
        """
        is_new = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        config = self._build_config(thread_id, session_id, user_id, model)

        # 상태 가드: 기존 thread가 interrupt 대기 중이면 /resume으로 유도
        if not is_new:
            current_state = await self.workflow.aget_state(config)
            if current_state and current_state.tasks:
                _logger.warning(
                    "chat_blocked_by_interrupt",
                    thread_id=thread_id,
                    tasks=[str(t) for t in current_state.tasks],
                )
                return {
                    "status": "waiting_for_user",
                    "interrupt_type": "product_selection",
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "recommended_products": (
                        current_state.values.get("intermediate", {})
                        .get("recommendation", {})
                        .get("recommended_products", [])
                    ),
                    "persona_info": (
                        current_state.values.get("intermediate", {})
                        .get("recommendation", {})
                        .get("persona_info")
                    ),
                    "messages": [],
                    "logs": [],
                    "error": "상품 선택이 필요합니다. /resume 엔드포인트를 사용해주세요.",
                }

        initial_state: SupervisorState = {
            "messages": [HumanMessage(content=user_input)]
        }

        try:
            result = await self.workflow.ainvoke(initial_state, config)

            # interrupt 감지 (CRM 상품 선택 대기)
            interrupts = result.get("__interrupt__", [])
            if interrupts:
                intermediate = result.get("intermediate", {})
                recommended_products = (
                    intermediate.get("recommendation", {})
                    .get("recommended_products", [])
                )
                persona_info = intermediate.get("recommendation", {}).get("persona_info")

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
            product_name = selected.get("product_name", selected_product_id)

            # interrupt 상태를 보존하기 위해 ainvoke 전에 aupdate_state 호출 금지
            result = await self.workflow.ainvoke(
                Command(resume=selected_product_id),
                config
            )

            # 워크플로우 완료 후 대화 이력 소급 저장
            # 1) interrupt AI 메시지 소급 저장
            product_names = [p.get("product_name", "") for p in recommended]
            interrupt_msg = (
                f"총 {len(product_names)}개 상품을 추천드렸습니다. "
                f"{', '.join(product_names)} 중 상품 하나를 선택해주세요."
            )
            await self.workflow.aupdate_state(
                config,
                {"messages": [AIMessage(content=interrupt_msg)]}
            )

            # 2) 사용자 선택 HumanMessage 저장
            await self.workflow.aupdate_state(
                config,
                {"messages": [HumanMessage(content=f"{product_name}을(를) 선택하겠습니다.")]}
            )

            # 3) 완료 AI 메시지 저장
            intermediate = result.get("intermediate", {})
            final_messages = intermediate.get("message", {}).get("messages", [])
            if final_messages:
                title = final_messages[0].get("title", "")
                await self.workflow.aupdate_state(
                    config,
                    {"messages": [AIMessage(content=f"CRM 메시지 생성이 완료되었습니다: {title}")]}
                )

            raw_status = result.get("status")
            api_status = "failed" if raw_status in ("failed", "quality_check_failed") else "completed"
            return {
                "status": api_status,
                "interrupt_type": None,
                "thread_id": thread_id,
                "session_id": session_id,
                "messages": final_messages,
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
