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
    from ..tools.parse_crm_request import parse_crm_message_request
except ImportError:
    import sys
    import os
    # 직접 실행 시 경로 추가
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tools.parse_crm_request import parse_crm_message_request

# Import recommend_products (상대 경로 지원)
try:
    from ..tools.basic_recommend_products import recommend_products
except ImportError:
    import sys
    import os
    # 직접 실행 시 경로 추가
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tools.basic_recommend_products import recommend_products

# Import create_product_message (상대 경로 지원)
try:
    from ..tools.create_product_message import create_product_message
except ImportError:
    import sys
    import os
    # 직접 실행 시 경로 추가
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tools.create_product_message import create_product_message

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
3. create_product_message: 선택된 상품으로 맞춤 메시지 생성
   - 입력: product (상품 정보), persona_info (페르소나 정보), purpose (메시지 목적)
   - 출력: title (제목), message (메시지 본문)

**워크플로우:**
1. parse_crm_message_request로 요청 파싱
2. recommend_products로 상품 추천 (persona_id만 제공)
3. status="interrupted" 반환 시:
   - merged_products 목록을 사용자에게 보여주고 작업 중단
   - 사용자 선택 대기 (외부에서 처리)

**인터럽트 워크플로우 사용 패턴:**
- 모든 인터럽트 워크플로우는 status 필드로 상태를 반환합니다
- status="interrupted": 사용자 입력 대기 중
  * 이 상태에서는 절대 recommend_products를 다시 호출하지 마세요
  * merged_products 목록을 사용자에게 보여주고 작업을 중단하세요
  * 사용자가 직접 선택할 때까지 기다려야 합니다
- status="completed": 작업 완료, 결과 사용 가능
- status="error": 오류 발생, error 필드 확인

**중요:**
- recommend_products를 1번만 호출하세요
- status="interrupted"가 반환되면, 더 이상 도구를 호출하지 말고 추천 상품 목록을 사용자에게 제시하세요
- 사용자 선택은 외부에서 처리되므로, 당신이 직접 선택하지 마세요
- create_product_message는 사용자 선택 후 외부에서 호출됩니다 (Agent에서 호출하지 않음)
"""

        # 시스템 프롬프트를 LLM에 바인딩
        self.llm_with_system = self.llm.bind(
            system=system_prompt
        )

        self.agent = create_react_agent(
            model=self.llm_with_system,
            tools=[
                parse_crm_message_request,
                recommend_products,
                create_product_message
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
            "persona_id": "PERSONA_002",
            "purpose": "신상품홍보",
            "brands": None,
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

            # 판매가 포맷팅 처리
            price = product.get('판매가', 'N/A')
            if isinstance(price, (int, float)):
                price_str = f"{price:,}원"
            else:
                price_str = f"{price}원" if price != 'N/A' else 'N/A'

            print(f"   - 가격: {price_str} (할인율: {product.get('할인율', 0)}%)")
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

            # 3단계: 메시지 생성
            print("\n[3단계] 메시지 생성 중...")
            print("=" * 80)

            # parse_crm_request 결과에서 persona_info 추출
            parsed_request = None
            for msg in messages:
                if msg.__class__.__name__ == "ToolMessage":
                    try:
                        tool_result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        if isinstance(tool_result, dict) and "persona_id" in tool_result:
                            parsed_request = tool_result
                            break
                    except:
                        pass

            # create_product_message 호출
            if parsed_request:
                message_result = create_product_message.invoke({
                    "product": selected_product,
                    "persona_info": parsed_request.get("persona_info", {}),
                    "purpose": parsed_request.get("purpose", "브랜드/제품 소개")
                })

                print(f"\n[생성된 CRM 메시지]")
                print("=" * 80)
                print(f"제목: {message_result.get('title', 'N/A')}")
                print(f"\n메시지:")
                print(message_result.get('message', 'N/A'))
                print("=" * 80)
            else:
                print("\n[에러] 파싱된 요청 정보를 찾을 수 없습니다.")
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
