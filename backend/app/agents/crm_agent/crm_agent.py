"""
CRM Agent

상품 추천 및 메시지 생성을 위한 CRM Agent
"""

from typing import Dict, Any, Optional
import uuid
from .state import CRMState
from .workflow import build_crm_workflow


class CRMAgent:
    """
    CRM Agent 클래스

    기능:
    - 사용자 요청 파싱 (페르소나, 브랜드, 카테고리, 목적 등)
    - 페르소나 기반 상품 추천 (상위 3개)
    - Human-in-the-loop: 사용자가 상품 선택
    - 선택된 상품에 대한 목적별 맞춤 메시지 생성
    """

    def __init__(self):
        """CRM Agent 초기화 (checkpointer 포함)"""
        self.workflow = build_crm_workflow()  # checkpointer 자동 설정됨
        print("[INFO] CRM Agent 초기화 완료 (Human-in-the-loop 지원)")

    def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        CRM Agent 실행 (초기 실행 또는 재개)

        Args:
            user_input: 사용자 입력 (예: "PERSONA_001로 설화수 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘")
            context: 실행 컨텍스트 (user_id, session_id 등)
            thread_id: 스레드 ID (재개 시 필요, None이면 새로운 스레드 생성)

        Returns:
            Dict[str, Any]: 실행 결과
            {
                "status": "waiting_for_user" | "completed" | "failed",
                "thread_id": str,  # 스레드 ID (재개 시 필요)
                "messages": [...],  # 생성된 메시지 리스트
                "recommended_products": [...],  # 추천된 상품 리스트 (사용자 선택 필요 시)
                "persona_info": {...},  # 페르소나 정보
                "logs": [...],  # 실행 로그
                "error": str | None  # 에러 메시지 (실패 시)
            }
        """
        # 스레드 ID 생성 (없으면)
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        # 초기 상태 생성
        initial_state: CRMState = {
            "input": user_input,
            "step": 0,
            "logs": [],
            "intermediate": {},
            "context": context or {},
            "status": "running",
            "selected_product_id": None,
            "waiting_for_user": False
        }

        try:
            # 워크플로우 실행 (thread_id 포함)
            config = {"configurable": {"thread_id": thread_id}}
            final_state = self.workflow.invoke(initial_state, config)

            # 결과 추출
            intermediate = final_state.get("intermediate", {})
            request = intermediate.get("request", {})
            recommendation = intermediate.get("recommendation", {})
            message = intermediate.get("message", {})

            # interrupt 상태 확인
            recommended_products = recommendation.get("recommended_products", [])
            if recommended_products and not message.get("messages"):
                # 추천 상품은 있지만 메시지가 없으면 사용자 입력 대기
                return {
                    "status": "waiting_for_user",
                    "thread_id": thread_id,
                    "messages": [],
                    "recommended_products": recommended_products,
                    "persona_info": recommendation.get("persona_info"),
                    "parsed_request": request.get("parsed_request"),
                    "analysis_id": recommendation.get("analysis_id"),
                    "queries": recommendation.get("queries", []),
                    "logs": final_state.get("logs", []),
                    "error": None,
                    "step": final_state.get("step", 0)
                }

            return {
                "status": final_state.get("status", "completed"),
                "thread_id": thread_id,
                "messages": message.get("messages", []),
                "recommended_products": recommended_products,
                "persona_info": recommendation.get("persona_info"),
                "parsed_request": request.get("parsed_request"),
                "analysis_id": recommendation.get("analysis_id"),
                "queries": recommendation.get("queries", []),
                "logs": final_state.get("logs", []),
                "error": final_state.get("error"),
                "step": final_state.get("step", 0)
            }

        except Exception as e:
            return {
                "status": "failed",
                "thread_id": thread_id,
                "messages": [],
                "recommended_products": [],
                "persona_info": None,
                "parsed_request": None,
                "analysis_id": None,
                "queries": [],
                "logs": [f"[ERROR] Agent 실행 실패: {str(e)}"],
                "error": str(e),
                "step": 0
            }

    def resume_with_selection(
        self,
        thread_id: str,
        selected_product_id: str
    ) -> Dict[str, Any]:
        """
        사용자 상품 선택 후 워크플로우 재개

        Args:
            thread_id: 스레드 ID (run() 메서드에서 반환된 값)
            selected_product_id: 사용자가 선택한 상품 ID

        Returns:
            Dict[str, Any]: 실행 결과 (메시지 생성 완료)
        """
        try:
            # 현재 상태 가져오기
            config = {"configurable": {"thread_id": thread_id}}
            current_state = self.workflow.get_state(config)

            # 상태 업데이트 (선택된 상품 ID 추가)
            updated_state = current_state.values.copy()
            updated_state["selected_product_id"] = selected_product_id
            updated_state["waiting_for_user"] = False

            # 워크플로우 재개 (None 입력으로 상태만 업데이트하고 계속 진행)
            self.workflow.update_state(config, updated_state)
            final_state = self.workflow.invoke(None, config)

            # 결과 추출
            intermediate = final_state.get("intermediate", {})
            request = intermediate.get("request", {})
            recommendation = intermediate.get("recommendation", {})
            message = intermediate.get("message", {})

            return {
                "status": final_state.get("status", "completed"),
                "thread_id": thread_id,
                "messages": message.get("messages", []),
                "recommended_products": recommendation.get("recommended_products", []),
                "persona_info": recommendation.get("persona_info"),
                "parsed_request": request.get("parsed_request"),
                "analysis_id": recommendation.get("analysis_id"),
                "queries": recommendation.get("queries", []),
                "logs": final_state.get("logs", []),
                "error": final_state.get("error"),
                "step": final_state.get("step", 0)
            }

        except Exception as e:
            return {
                "status": "failed",
                "thread_id": thread_id,
                "messages": [],
                "recommended_products": [],
                "persona_info": None,
                "parsed_request": None,
                "analysis_id": None,
                "queries": [],
                "logs": [f"[ERROR] Agent 재개 실패: {str(e)}"],
                "error": str(e),
                "step": 0
            }

    async def arun(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        CRM Agent 비동기 실행

        Args:
            user_input: 사용자 입력
            context: 실행 컨텍스트

        Returns:
            Dict[str, Any]: 실행 결과
        """
        # 초기 상태 생성
        initial_state: CRMState = {
            "input": user_input,
            "step": 0,
            "logs": [],
            "intermediate": {},
            "context": context or {},
            "status": "running"
        }

        try:
            # 워크플로우 비동기 실행
            final_state = await self.workflow.ainvoke(initial_state)

            # 결과 추출
            intermediate = final_state.get("intermediate", {})
            request = intermediate.get("request", {})
            recommendation = intermediate.get("recommendation", {})
            message = intermediate.get("message", {})

            return {
                "status": final_state.get("status", "completed"),
                "messages": message.get("messages", []),
                "recommended_products": recommendation.get("recommended_products", []),
                "persona_info": recommendation.get("persona_info"),
                "parsed_request": request.get("parsed_request"),
                "analysis_id": recommendation.get("analysis_id"),
                "queries": recommendation.get("queries", []),
                "logs": final_state.get("logs", []),
                "error": final_state.get("error"),
                "step": final_state.get("step", 0)
            }

        except Exception as e:
            return {
                "status": "failed",
                "messages": [],
                "recommended_products": [],
                "persona_info": None,
                "parsed_request": None,
                "analysis_id": None,
                "queries": [],
                "logs": [f"[ERROR] Agent 실행 실패: {str(e)}"],
                "error": str(e),
                "step": 0
            }


if __name__ == "__main__":
    """CRM Agent 테스트 (Human-in-the-loop)"""
    import sys
    import io
    from pprint import pprint

    # Windows 인코딩 문제 해결
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("=" * 80)
    print("CRM Agent 테스트 (Human-in-the-loop)")
    print("=" * 80)

    # Agent 생성
    agent = CRMAgent()

    # 테스트 입력
    test_input = "PERSONA_001로 설화수 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘"

    print(f"\n[입력]")
    print(f"  {test_input}")

    # ========================================
    # 1단계: 초기 실행 (상품 추천까지)
    # ========================================
    print("\n" + "=" * 80)
    print("1단계: Agent 실행 (상품 추천까지)")
    print("=" * 80)

    result = agent.run(
        user_input=test_input,
        context={
            "user_id": "test_user",
            "session_id": "test_session"
        }
    )

    print(f"\nStatus: {result.get('status')}")
    print(f"Thread ID: {result.get('thread_id')}")

    if result.get('status') == 'waiting_for_user':
        # 사용자 입력 대기 상태
        print("\n" + "=" * 80)
        print("상품 추천 완료 - 사용자 선택 대기 중")
        print("=" * 80)

        print(f"\n[파싱 결과]")
        pprint(result.get('parsed_request'), indent=2)

        recommended_products = result.get('recommended_products', [])

        # ========================================
        # 2단계: 사용자에게 상품 리스트 표시 및 선택
        # ========================================
        print("\n" + "=" * 80)
        print("📦 추천 상품 목록")
        print("=" * 80)

        for i, product in enumerate(recommended_products, 1):
            print(f"\n┌{'─' * 60}")
            print(f"│  [{i}] {product.get('product_name')}")
            print(f"├{'─' * 60}")
            print(f"│  상품ID: {product.get('product_id')}")
            print(f"│  브랜드: {product.get('brand')}")
            print(f"│  가격: {product.get('sale_price'):,}원")
            if product.get('original_price') and product.get('original_price') != product.get('sale_price'):
                discount = int((1 - product.get('sale_price') / product.get('original_price')) * 100)
                print(f"│  정가: {product.get('original_price'):,}원 ({discount}% 할인)")
            if product.get('category'):
                print(f"│  카테고리: {product.get('category')}")
            print(f"│  적합도: {'⭐' * min(5, int(product.get('vector_search_score', 0) * 5 + 0.5))} ({product.get('vector_search_score', 0):.2f})")
            print(f"└{'─' * 60}")

        print(f"\n총 {len(recommended_products)}개의 상품이 추천되었습니다.")
        print("-" * 80)

        # 사용자가 상품 선택 (입력 받기)
        while True:
            try:
                user_input = input(f"\n👉 메시지를 생성할 상품 번호를 선택하세요 (1-{len(recommended_products)}): ")
                selected_index = int(user_input) - 1  # 1-based를 0-based로 변환
                if 0 <= selected_index < len(recommended_products):
                    break
                else:
                    print(f"❌ 잘못된 입력입니다. 1부터 {len(recommended_products)} 사이의 숫자를 입력하세요.")
            except ValueError:
                print("❌ 숫자를 입력하세요.")

        selected_product = recommended_products[selected_index]
        selected_product_id = selected_product.get('product_id')
        print(f"\n✅ 선택된 상품: [{selected_index + 1}] {selected_product.get('product_name')} ({selected_product.get('brand')}) - {selected_product.get('sale_price'):,}원")

        print("\n" + "=" * 80)
        print("3단계: 워크플로우 재개 (메시지 생성)")
        print("=" * 80)

        # 워크플로우 재개
        thread_id = result.get('thread_id')
        final_result = agent.resume_with_selection(
            thread_id=thread_id,
            selected_product_id=selected_product_id
        )

        print(f"\nStatus: {final_result.get('status')}")

        if final_result.get('status') == 'completed':
            print("\n" + "=" * 80)
            print("메시지 생성 완료")
            print("=" * 80)

            print(f"\n[생성된 메시지] {len(final_result.get('messages', []))}개")
            for i, msg in enumerate(final_result.get('messages', []), 1):
                print(f"\n  [메시지 {i}]")
                print(f"  상품: {msg.get('product_name')} ({msg.get('brand')})")
                print(f"  제목: {msg.get('title')}")
                print(f"  가격: {msg.get('sale_price'):,}원")
                print(f"\n  메시지 내용:")
                print("  " + "-" * 76)
                print(f"  {msg.get('message')}")
                print("  " + "-" * 76)
                print(f"  URL: {msg.get('product_url')}")
                print(f"  Vector Score: {msg.get('vector_search_score', 0):.3f}")

            print("\n" + "=" * 80)
            print("전체 실행 로그")
            print("=" * 80)
            for log in final_result.get('logs', []):
                print(f"  {log}")

        else:
            print(f"\n[ERROR] 메시지 생성 실패: {final_result.get('error')}")

    elif result.get('status') == 'completed':
        # 바로 완료된 경우 (선택 없이 바로 메시지 생성)
        print("\n[경고] 바로 완료됨 - Human-in-the-loop가 작동하지 않았습니다")
        print(f"\n[생성된 메시지] {len(result.get('messages', []))}개")

    else:
        # 에러 발생
        print(f"\n[ERROR] {result.get('error')}")
        print("\n실행 로그:")
        for log in result.get('logs', []):
            print(f"  {log}")