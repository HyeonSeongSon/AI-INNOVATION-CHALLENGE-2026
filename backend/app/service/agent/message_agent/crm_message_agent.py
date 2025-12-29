"""
Hierarchical Agent 방식
워크플로우를 Tool로 감싸서 ReAct Agent가 사용
"""

from typing import Dict, Any
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
import os
import sys
import uuid

# 직접 실행 시 경로 추가
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)

# Import the parsing tool (상대 경로 지원)
try:
    from .tools.parse_crm_request import parse_crm_message_request
except ImportError:
    from tools.parse_crm_request import parse_crm_message_request

# Import recommend_products (상대 경로 지원)
try:
    from .crm_message_with_interrupt import recommend_products
except ImportError:
    from crm_message_with_interrupt import recommend_products

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


# ============================================================
# Hierarchical Agent
# ============================================================

class CRMMessageHierarchicalAgent:
    def __init__(self):
        self.checkpointer = MemorySaver()

        # LLM 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0.7,
            api_key=api_key
        )

        # 시스템 프롬프트
        system_prompt = """
당신은 CRM 메시지 생성 전문가입니다.

**목표**:
사용자의 요청을 분석하고, 적절한 상품을 추천하며, 고품질 CRM 메시지를 생성하세요.

**사용 가능한 도구:**
1. parse_crm_message_request: 사용자 요청을 구조화된 데이터로 파싱 (자연어/JSON 지원)
2. recommend_products: 상품 추천 워크플로우 (인터럽트 지원)
   - 1차 호출: persona_id 제공 → status="interrupted", merged_products 반환
   - 2차 호출: thread_id + selected_index 제공 → status="completed", selected_product 반환

**인터럽트 워크플로우 사용 패턴:**
- 모든 인터럽트 워크플로우는 status 필드로 상태를 반환합니다
- status="interrupted": 사용자 입력 대기 중, thread_id를 저장하고 사용자에게 선택 요청
- status="completed": 작업 완료, 결과 사용 가능
- status="error": 오류 발생, error 필드 확인

**중요:**
- 최종 답변은 생성된 메시지 텍스트를 사용자에게 제공하는 것으로 마무리하세요.
- 불필요한 도구 호출을 반복하지 마세요.
"""

        # 시스템 프롬프트를 LLM에 바인딩
        self.llm_with_system = self.llm.bind(
            system=system_prompt
        )

        self.agent = create_react_agent(
            model=self.llm_with_system,
            tools=[
                parse_crm_message_request,
                recommend_products
            ],
            checkpointer=self.checkpointer
        )

    def generate(self, user_request: str = None, **kwargs) -> Dict[str, Any]:
        """
        메시지 생성

        Args:
            user_request: 자연어 요청 또는 JSON (선택)
            **kwargs: 개별 파라미터 (user_request가 없을 때 사용)
        """
        session_id = str(uuid.uuid4())
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": 50  # 재귀 한도 증가
        }

        # 자연어 요청이 있으면 그대로 사용, 없으면 기존 방식
        if user_request:
            user_input = user_request
        else:
            user_input = f"""
페르소나 ID: {kwargs['persona_id']}
목적: {kwargs['purpose']}
카테고리: {kwargs['product_category']}
브랜드: {kwargs['brand']}
전용제품: {kwargs['exclusive_product']}

위 정보로 CRM 메시지를 생성해주세요.
"""

        result = self.agent.invoke(
            {"messages": [("user", user_input)]},
            config=config
        )

        # 결과 파싱
        return self._parse_result(result)

    def _parse_result(self, result):
        """
        에이전트 실행 결과를 파싱하여 사용자 친화적인 형태로 변환

        Args:
            result: agent.invoke()의 반환값

        Returns:
            파싱된 결과 딕셔너리
        """
        # LangGraph 에이전트 결과 구조:
        # result = {
        #     "messages": [
        #         HumanMessage(...),
        #         AIMessage(content="...", tool_calls=[...]),
        #         ToolMessage(...),
        #         ...
        #         AIMessage(content="최종 답변")
        #     ]
        # }

        messages = result.get("messages", [])

        # 최종 AI 메시지 추출 (마지막 AIMessage)
        final_message = None
        tool_calls_log = []

        for msg in messages:
            msg_type = msg.__class__.__name__

            if msg_type == "AIMessage":
                # AI 메시지와 도구 호출 기록
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_calls_log.append({
                            "tool": tool_call.get("name", "unknown"),
                            "args": tool_call.get("args", {})
                        })

                # 최종 응답 (도구 호출이 없는 마지막 AI 메시지)
                if msg.content and not (hasattr(msg, 'tool_calls') and msg.tool_calls):
                    final_message = msg.content

        # 도구 호출 결과 수집
        generated_message = None
        review_score = None
        selected_product = None

        for msg in messages:
            if msg.__class__.__name__ == "ToolMessage":
                # ToolMessage의 content는 도구 실행 결과 (문자열)
                try:
                    import json
                    tool_result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content

                    # 메시지 생성 결과 확인
                    if isinstance(tool_result, dict) and "message" in tool_result:
                        generated_message = tool_result["message"]

                    # 검토 점수 확인
                    if isinstance(tool_result, dict) and "score" in tool_result:
                        review_score = tool_result["score"]

                    # 선택된 상품 확인
                    if isinstance(tool_result, dict) and "selected_product" in tool_result:
                        selected_product = tool_result["selected_product"]

                except:
                    pass

        return {
            "success": True,
            "final_response": final_message or generated_message or "메시지 생성 완료",
            "message": generated_message,
            "review_score": review_score,
            "selected_product": selected_product,
            "tool_calls": tool_calls_log,
            "llm_calls": len([t for t in tool_calls_log if t]),
            "raw_result": result  # 디버깅용
        }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # Windows 콘솔 UTF-8 인코딩 설정
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("=== Hierarchical Agent 방식 테스트 ===\n")

    agent = CRMMessageHierarchicalAgent()    

    # 테스트
    print("[테스트]")
    print("=" * 80)
    result2 = agent.generate(
        # user_request="페르소나 P456으로 신상품홍보목적으로 에스쁘아브랜드의 립스틱 광고메세지를 생성해줘"
        user_request="""{
            "persona_id": "P456",
            "purpose": "신상품홍보",
            "brands": ["에스쁘아"],
            "product_categories": ["립스틱"],
            "exclusive_target": None
        }"""
    )

    print("\n[도구 호출 내역]")
    for i, tool_call in enumerate(result2.get('tool_calls', []), 1):
        print(f"  {i}. {tool_call['tool']}")

    print(f"\n[최종 응답]")
    print("-" * 70)
    print(result2.get('final_response', ''))
    print("-" * 70)

    # raw_result에서 도구 결과 확인
    import json
    interrupted_data = None
    thread_id = None

    messages = result2.get('raw_result', {}).get('messages', [])
    for msg in messages:
        if msg.__class__.__name__ == "ToolMessage":
            try:
                tool_result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(tool_result, dict) and tool_result.get('status') == 'interrupted':
                    interrupted_data = tool_result
                    thread_id = tool_result.get('thread_id')
                    break
            except:
                pass

    # 인터럽트 상태인 경우 사용자 선택 받기
    if interrupted_data and thread_id:
        print("\n" + "=" * 80)
        print("[사용자 인터럽트] 상품 추천 완료, 선택이 필요합니다")
        print("=" * 80)

        merged_products = interrupted_data.get('merged_products', [])

        print(f"\n[추천 상품 목록] (총 {len(merged_products)}개)")
        for idx, product in enumerate(merged_products):
            print(f"\n{idx}. {product.get('상품명', 'N/A')}")
            print(f"   - 브랜드: {product.get('브랜드', 'N/A')}")
            print(f"   - 가격: {product.get('판매가', 'N/A'):,}원 (할인율: {product.get('할인율', 0)}%)")
            print(f"   - 별점: {product.get('별점', 'N/A')} ({product.get('리뷰_갯수', 0)}개 리뷰)")
            print(f"   - 벡터 검색 점수: {product.get('vector_search_score', 'N/A')}")

        # 사용자 입력 받기
        print("\n" + "=" * 80)
        while True:
            try:
                user_input = input(f"선택할 상품 번호를 입력하세요 (0-{len(merged_products)-1}): ")
                selected_index = int(user_input)

                if 0 <= selected_index < len(merged_products):
                    print(f"[사용자 선택] {selected_index}번 상품 선택")
                    break
                else:
                    print(f"잘못된 번호입니다. 0부터 {len(merged_products)-1} 사이의 숫자를 입력하세요.")
            except ValueError:
                print("숫자를 입력해주세요.")
            except KeyboardInterrupt:
                print("\n프로그램을 종료합니다.")
                exit(0)

        # 선택 완료 후 Agent 재실행
        print("\n[2단계] 사용자 선택 반영 중...")
        print("=" * 80)

        # recommend_products 도구를 직접 호출하여 선택 완료
        final_result = recommend_products.invoke({
            "thread_id": thread_id,
            "selected_index": selected_index
        })

        if final_result.get("status") == "completed":
            selected_product = final_result.get("selected_product", {})
            print(f"\n[선택 완료]")
            print(f"  상품명: {selected_product.get('상품명', 'N/A')}")
            print(f"  브랜드: {selected_product.get('브랜드', 'N/A')}")
            print(f"  가격: {selected_product.get('판매가', 'N/A'):,}원")
            print(f"  벡터 검색 점수: {selected_product.get('vector_search_score', 'N/A')}")
        else:
            print(f"\n[에러] {final_result.get('error', '알 수 없는 오류')}")
    else:
        # 인터럽트가 없는 경우 일반 결과 출력
        if result2.get('message'):
            print(f"\n[생성된 메시지]")
            print("-" * 70)
            print(result2['message'])
            print("-" * 70)

        if result2.get('selected_product'):
            print(f"\n선택된 상품: {result2['selected_product'].get('product_name', 'N/A')}")
        if result2.get('review_score'):
            print(f"검토 점수: {result2['review_score']}")

    print(f"\nLLM 호출 횟수: {result2.get('llm_calls', 0)}")
