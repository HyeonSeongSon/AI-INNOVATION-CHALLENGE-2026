"""
CRM 메시지 생성 에이전트 - Tool Calling 방식
요구사항 문서(crm_interrupt_requirements.md) 기반 구현
"""

from typing import Dict, Any, Optional, TypedDict
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
import os
import sys
import json


# ============================================================
# Custom State 정의
# ============================================================

class CRMState(MessagesState):
    """CRM Agent용 커스텀 스테이트"""
    selected_product_id: Optional[str] = None

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

# Tools import
try:
    from ...tools.parse_crm_request import parse_crm_message_request
    from ...tools.recommend_products_persona_tool import recommend_products_persona
    from ...tools.create_product_message import create_product_message
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from tools.parse_crm_request import parse_crm_message_request
    from tools.recommend_products_persona_tool import recommend_products_persona
    from tools.create_product_message import create_product_message


# ============================================================
# Tool Calling Agent
# ============================================================

class CRMMessageAgent:
    """Tool Calling 방식의 CRM 메시지 생성 에이전트"""

    def __init__(self):
        """Tool Calling 방식의 CRM 메시지 생성 에이전트 초기화"""
        # LLM 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0.7,
            api_key=api_key
        )

        # 도구 목록
        self.tools = [
            parse_crm_message_request,
            recommend_products_persona,
            create_product_message
        ]

        # 시스템 프롬프트
        self.system_message = """당신은 CRM 메시지 생성 전문가입니다.

**목표**: 사용자의 요청을 분석하고, 적절한 상품을 추천하며, 고품질 CRM 메시지를 생성하세요.

**작업 방식**:
- 사용 가능한 도구들의 설명(description)을 주의 깊게 읽으세요
- 각 도구의 "언제 사용하나요?" 섹션을 확인하여 현재 상황에 맞는 도구를 선택하세요
- 도구의 description에는 언제 사용해야 하는지, 어떤 입력이 필요한지가 명시되어 있습니다

**🔥 핵심 규칙 - 도구 결과 재사용 🔥**:
이전에 도구를 실행한 결과가 있다면, 그 결과를 **절대 수정하지 말고 정확히 그대로** 다음 도구에 전달하세요.

예시:
- `parse_crm_message_request` 실행 결과:
  {
    "persona_id": "PERSONA_001",
    "purpose": "브랜드/제품 첫소개",
    "brands": ["에스쁘아"],
    "product_categories": ["메이크업-립스틱"],
    "exclusive_target": null
  }

- `recommend_products_persona` 호출할 때:
  ✅ 올바른 방법: 파서 결과를 **그대로** 사용
    recommend_products_persona(
      persona_id="PERSONA_001",           # 파서 결과 그대로
      user_input="에스쁘아 립스틱 제품 소개",
      brands=["에스쁘아"],                # 파서 결과 그대로
      product_categories=["메이크업-립스틱"]  # 파서 결과 그대로
    )

  ❌ 잘못된 방법: 자신이 추론하거나 수정
    recommend_products_persona(
      persona_id="PERSONA_002",  # ❌ 파서는 001이라고 했는데 변경
      brands=["에스쁘아", "헤라"],  # ❌ 파서에 없던 브랜드 추가
      product_categories=["립스틱"]  # ❌ 파서는 "메이크업-립스틱"이라고 했는데 변경
    )

**중요 규칙**:
1. 같은 도구를 여러 번 호출하지 마세요
2. 이전 도구의 실행 결과가 있으면 **반드시 그 결과를 그대로** 사용하세요
3. 도구 실행 결과를 확인하고, 다음에 필요한 도구가 무엇인지 판단하세요
4. 사용자의 추가 입력이 필요한 경우 대기하세요
"""

        # LLM에 도구 바인딩
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # 체크포인터 설정 (MemorySaver 사용)
        self.checkpointer = MemorySaver()

        # 그래프 구성
        self.app = self._build_graph()

    def _build_graph(self):
        """StateGraph 구성"""

        # Agent 노드: LLM이 도구를 선택하고 호출
        def agent_node(state: CRMState):
            """LLM이 상황에 맞는 도구를 선택"""
            from langchain_core.messages import SystemMessage

            # 시스템 메시지 주입
            messages = state['messages']
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=self.system_message)] + messages

            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        # Tool 노드
        tool_node = ToolNode(self.tools)

        # 조건부 엣지: 다음 단계 결정
        def should_continue(state: CRMState):
            last_message = state['messages'][-1]

            # 도구 호출이 없으면 종료
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                return END

            # recommend_products_persona 도구가 호출되었는지 확인
            tool_names = [tc['name'] for tc in last_message.tool_calls]

            if 'recommend_products_persona' in tool_names:
                # 제품 추천 후 → Interrupt 발생시킬 노드로 이동
                return "wait_for_selection"

            # 다른 도구들은 바로 실행
            return "tools"

        # 그래프 구성
        workflow = StateGraph(CRMState)

        # 노드 추가
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("wait_for_selection", lambda state: state)  # Interrupt 지점

        # 엣지 설정
        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "wait_for_selection": "tools",  # tools 먼저 실행
                END: END
            }
        )

        # tools 실행 후 조건부 분기
        def after_tools(state: CRMState):
            """tools 실행 후 다음 단계 결정"""
            # 이전 AI 메시지에서 recommend_products_persona 호출 여부 확인
            messages = state['messages']
            for msg in reversed(messages):
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    tool_names = [tc['name'] for tc in msg.tool_calls]
                    if 'recommend_products_persona' in tool_names:
                        return "wait_for_selection"
                    break

            return "agent"

        workflow.add_conditional_edges(
            "tools",
            after_tools,
            {
                "agent": "agent",
                "wait_for_selection": "wait_for_selection"
            }
        )

        # wait_for_selection 이후에도 agent로 (사용자 선택 반영 후)
        workflow.add_edge("wait_for_selection", "agent")

        # 컴파일 - wait_for_selection 노드 전에 Interrupt
        return workflow.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["wait_for_selection"]  # 🔑 핵심!
        )

    def generate(self, user_input: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        1단계: CRM 메시지 생성 시작 (상품 추천까지)

        Args:
            user_input: 사용자 입력 (JSON 또는 자연어)
            thread_id: 세션 ID (선택)

        Returns:
            {
                "status": "needs_selection" | "completed" | "error",
                "thread_id": str,
                "recommended_products": List[Dict],  # needs_selection 시
                "final_message": str,  # completed 시
                ...
            }
        """
        import uuid
        thread_id = thread_id or f"thread-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # Agent 실행
            result = self.app.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config
            )

            # 상태 확인
            state = self.app.get_state(config)

            # Interrupt 확인 (state.next는 튜플)
            if state.next and "wait_for_selection" in state.next:
                # 메시지 히스토리에서 recommend_products_persona 결과 추출
                messages = state.values['messages']

                # recommend_products_persona의 ToolMessage 찾기
                products_result = self._extract_tool_result(messages, 'recommend_products_persona')

                if products_result:
                    # JSON 파싱
                    try:
                        products_data = json.loads(products_result)
                    except Exception as e:
                        products_data = products_result

                    return {
                        "status": "needs_selection",
                        "thread_id": thread_id,
                        "persona_info": products_data.get("persona_info"),
                        "search_query": products_data.get("search_query"),
                        "recommended_products": products_data.get("products", []),
                        "count": products_data.get("count", 0)
                    }

            # 정상 완료
            final_msg = self._get_last_ai_message(state.values['messages'])
            return {
                "status": "completed",
                "thread_id": thread_id,
                "final_message": final_msg
            }

        except Exception as e:
            return {
                "status": "error",
                "thread_id": thread_id,
                "error": str(e)
            }

    def select_product(self, thread_id: str, selected_product_id: str) -> Dict[str, Any]:
        """
        2단계: 사용자 제품 선택 처리

        Args:
            thread_id: 1단계에서 받은 세션 ID
            selected_product_id: 선택한 제품 ID

        Returns:
            {
                "status": "completed" | "error",
                "final_message": Dict,
                "selected_product": Dict
            }
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # 현재 상태 확인
            state = self.app.get_state(config)

            if not state.next:
                return {
                    "status": "error",
                    "error": "이미 완료되었거나 유효하지 않은 세션입니다."
                }

            # 추천된 제품 목록에서 선택한 제품 찾기
            messages = state.values['messages']
            products_result = self._extract_tool_result(messages, 'recommend_products_persona')

            try:
                products_data = json.loads(products_result)
            except:
                products_data = products_result

            products = products_data.get("products", [])
            selected = next(
                (p for p in products if p.get('product_id') == selected_product_id),
                None
            )

            if not selected:
                return {
                    "status": "error",
                    "error": f"선택한 제품을 찾을 수 없습니다: {selected_product_id}"
                }

            # 🔑 핵심: 사용자 선택을 HumanMessage로 추가 + selected_product_id를 state에 저장
            selection_message = HumanMessage(
                content=f"사용자가 다음 제품을 선택했습니다: {json.dumps(selected, ensure_ascii=False)}"
            )

            # 상태에 메시지와 selected_product_id 추가
            self.app.update_state(
                config,
                {
                    "messages": [selection_message],
                    "selected_product_id": selected_product_id
                }
            )

            # Agent 재개
            result = self.app.invoke(None, config=config)

            # 최종 결과 확인
            final_state = self.app.get_state(config)

            # create_product_message 결과 추출
            final_msg_result = self._extract_tool_result(final_state.values['messages'], 'create_product_message')

            if final_msg_result:
                try:
                    final_msg = json.loads(final_msg_result)
                except:
                    final_msg = final_msg_result
            else:
                final_msg = self._get_last_ai_message(final_state.values['messages'])

            return {
                "status": "completed",
                "thread_id": thread_id,
                "final_message": final_msg,
                "selected_product": selected
            }

        except Exception as e:
            return {
                "status": "error",
                "thread_id": thread_id,
                "error": str(e)
            }

    def _extract_tool_result(self, messages, tool_name: str):
        """메시지 히스토리에서 특정 도구의 결과 추출"""
        for msg in reversed(messages):
            # ToolMessage 찾기
            if hasattr(msg, 'name') and msg.name == tool_name:
                # 도구 실행 결과는 content에 저장됨
                return msg.content
        return None

    def _get_last_ai_message(self, messages):
        """마지막 AI 메시지 추출"""
        for msg in reversed(messages):
            if hasattr(msg, 'type') and msg.type == 'ai' and msg.content:
                return msg.content
        return None


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # Windows 콘솔 UTF-8 인코딩 설정
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("=== Tool Calling 방식 CRM Agent 테스트 ===\n")

    agent = CRMMessageAgent()

    # 1단계: 상품 추천까지
    print("[1단계] CRM 메시지 생성 시작")
    print("=" * 80)

    user_input = "PERSONA_002 페르소나로 브랜드홍보 목적으로 에스쁘아 립스틱 광고메세지를 생성해줘"
    # user_input = """{
    #     "persona_id": "PERSONA_002",
    #     "purpose": "신상품홍보",
    #     "brands": null,
    #     "product_categories": ["립스틱"],
    #     "exclusive_target": null
    # }"""

    result = agent.generate(user_input)

    print(f"\n[상태]: {result.get('status')}")
    print(f"[Thread ID]: {result.get('thread_id')}")

    # LLM 호출 횟수 계산
    config = {"configurable": {"thread_id": result.get('thread_id')}}
    state = agent.app.get_state(config)
    messages = state.values.get('messages', [])

    llm_call_count = sum(1 for msg in messages if hasattr(msg, 'type') and msg.type == 'ai')
    tool_call_count = sum(1 for msg in messages if hasattr(msg, 'type') and msg.type == 'tool')

    print(f"[LLM 호출 횟수]: {llm_call_count}회")
    print(f"[Tool 실행 횟수]: {tool_call_count}회")

    if result.get("status") == "needs_selection":
        products = result.get('recommended_products', [])
        print(f"\n[추천 상품] ({len(products)}개)")

        for idx, product in enumerate(products):
            print(f"\n{idx}. {product.get('product_name', 'N/A')}")
            print(f"   - 브랜드: {product.get('brand', 'N/A')}")

            # 가격 포맷팅
            price = product.get('sale_price', 'N/A')
            if isinstance(price, (int, float)):
                print(f"   - 가격: {price:,}원")
            else:
                print(f"   - 가격: {price}")

            print(f"   - 점수: {product.get('vector_search_score', 'N/A')}")

        # 사용자 입력
        print("\n" + "=" * 80)
        while True:
            try:
                user_choice = input(f"선택할 상품 번호 (0-{len(products)-1}): ")
                choice_idx = int(user_choice)

                if 0 <= choice_idx < len(products):
                    selected_product_id = products[choice_idx].get('product_id')
                    break
                else:
                    print(f"잘못된 번호입니다. 0-{len(products)-1} 사이의 숫자를 입력하세요.")
            except ValueError:
                print("숫자를 입력해주세요.")
            except KeyboardInterrupt:
                print("\n종료합니다.")
                exit(0)

        # 2단계: 사용자 선택 처리
        print("\n[2단계] 제품 선택 및 메시지 생성")
        print("=" * 80)

        final_result = agent.select_product(
            thread_id=result['thread_id'],
            selected_product_id=selected_product_id
        )

        if final_result.get("status") == "completed":
            selected = final_result.get("selected_product", {})
            message = final_result.get("final_message", {})

            # 최종 LLM 호출 횟수 계산
            final_config = {"configurable": {"thread_id": result['thread_id']}}
            final_state = agent.app.get_state(final_config)
            final_messages = final_state.values.get('messages', [])

            final_llm_call_count = sum(1 for msg in final_messages if hasattr(msg, 'type') and msg.type == 'ai')
            final_tool_call_count = sum(1 for msg in final_messages if hasattr(msg, 'type') and msg.type == 'tool')

            print(f"\n[최종 통계]")
            print(f"  - 총 LLM 호출 횟수: {final_llm_call_count}회")
            print(f"  - 총 Tool 실행 횟수: {final_tool_call_count}회")

            print(f"\n[선택된 제품]")
            print(f"  - 상품명: {selected.get('product_name', 'N/A')}")
            print(f"  - 브랜드: {selected.get('brand', 'N/A')}")

            print(f"\n[생성된 CRM 메시지]")
            print("=" * 80)
            if isinstance(message, dict):
                print(f"제목: {message.get('title', 'N/A')}")
                print(f"\n메시지:\n{message.get('message', 'N/A')}")
            else:
                print(message)
            print("=" * 80)
        else:
            print(f"\n[에러] {final_result.get('error')}")
    else:
        print(f"\n예상치 못한 상태: {result.get('status')}")
