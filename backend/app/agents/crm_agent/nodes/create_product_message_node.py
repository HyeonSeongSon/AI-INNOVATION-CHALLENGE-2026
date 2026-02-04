"""
상품 메시지 생성 노드

추천된 상품들에 대해 목적별 맞춤 메시지를 생성하는 노드
"""

from typing import Dict, Any
from ..state import CRMState
from ..services.create_product_message import ProductMessageGenerator


# Generator 싱글톤 인스턴스 (재사용)
_generator_instance = None


def get_message_generator() -> ProductMessageGenerator:
    """MessageGenerator 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ProductMessageGenerator()
    return _generator_instance


def create_product_message_node(state: CRMState) -> Dict[str, Any]:
    """
    추천된 상품들에 대해 메시지를 생성하는 노드

    사용자가 선택한 상품에 대해서만 메시지를 생성합니다.

    Args:
        state: CRMState - 현재 상태

    Returns:
        Dict[str, Any]: 업데이트할 상태

    State 업데이트:
        - intermediate.message.messages: 생성된 메시지 리스트
        - logs: 실행 로그 추가
        - step: step 증가
        - last_node: 현재 노드명 기록
        - current_node: 다음 노드로 업데이트
    """

    # 현재 step과 로그 초기화
    current_step = state.get("step", 0)
    logs = state.get("logs", [])
    intermediate = state.get("intermediate", {})

    # 로그 추가
    logs.append(f"[Step {current_step}] create_product_message_node 시작")

    try:
        # 1. 필요한 데이터 가져오기 (Context 구조)
        request_context = intermediate.get("request", {})
        recommendation_context = intermediate.get("recommendation", {})

        parsed_request = request_context.get("parsed_request")
        persona_info = recommendation_context.get("persona_info")
        recommended_products = recommendation_context.get("recommended_products", [])

        # 사용자가 선택한 상품 ID 가져오기
        selected_product_id = state.get("selected_product_id")

        # Context 구조 초기화
        if "message" not in intermediate:
            intermediate["message"] = {}

        if not recommended_products:
            logs.append(f"[Step {current_step}] 추천된 상품이 없습니다.")
            intermediate["message"]["messages"] = []

            return {
                "step": current_step + 1,
                "last_node": "create_product_message_node",
                "current_node": "end",  # 상품이 없으면 종료
                "intermediate": intermediate,
                "logs": logs,
                "status": "completed"
            }

        if not persona_info:
            raise ValueError("페르소나 정보가 없습니다.")

        if not parsed_request:
            raise ValueError("파싱된 요청 정보가 없습니다.")

        # 사용자 선택 확인 (필수)
        if selected_product_id is None:
            logs.append(f"[Step {current_step}] ERROR: 사용자가 상품을 선택하지 않았습니다.")
            raise ValueError("사용자가 상품을 선택하지 않았습니다. selected_product_id가 필요합니다.")

        # 선택된 상품 ID로 상품 찾기
        selected_product = None
        for product in recommended_products:
            if product.get("product_id") == selected_product_id:
                selected_product = product
                break

        if selected_product is None:
            logs.append(f"[Step {current_step}] ERROR: 상품 ID '{selected_product_id}'를 찾을 수 없습니다.")
            raise ValueError(f"상품 ID '{selected_product_id}'를 찾을 수 없습니다.")

        logs.append(f"[Step {current_step}] 사용자 선택 상품: {selected_product_id} - {selected_product.get('product_name')}")

        # 목적 가져오기
        purpose = parsed_request.get("purpose", "브랜드/제품 소개")
        logs.append(f"[Step {current_step}] 메시지 생성 목적: {purpose}")

        # 2. MessageGenerator 가져오기
        generator = get_message_generator()

        # 3. 선택된 상품에 대해 메시지 생성
        messages = []
        product_name = selected_product.get("product_name", "알 수 없음")
        logs.append(f"[Step {current_step}] 메시지 생성 중: {product_name}")

        # 메시지 생성
        message_result = generator.generate_message(
            product=selected_product,
            persona_info=persona_info,
            purpose=purpose
        )

        if message_result.get("success"):
            # 생성 성공
            message_data = {
                "product_id": selected_product.get("product_id"),
                "product_name": selected_product.get("product_name"),
                "brand": selected_product.get("brand"),
                "title": message_result.get("title", ""),
                "message": message_result.get("message", ""),
                "full_content": message_result.get("full_content", ""),
                "purpose": purpose,
                "vector_search_score": selected_product.get("vector_search_score", 0),
                "product_url": selected_product.get("product_page_url", ""),
                "sale_price": selected_product.get("sale_price", 0)
            }
            messages.append(message_data)
            logs.append(f"[Step {current_step}] 메시지 생성 완료")
        else:
            # 생성 실패
            error_msg = message_result.get("error", "알 수 없는 오류")
            logs.append(f"[Step {current_step}] 메시지 생성 실패: {error_msg}")

        # 4. Context 구조로 결과 저장
        logs.append(f"[Step {current_step}] 전체 메시지 생성 완료: {len(messages)}개")
        intermediate["message"]["messages"] = messages

        # 상태 업데이트
        return {
            "step": current_step + 1,
            "last_node": "create_product_message_node",
            "current_node": "end",  # 메시지 생성 완료 후 종료
            "intermediate": intermediate,
            "logs": logs,
            "status": "completed"
        }

    except Exception as e:
        # 에러 처리
        error_msg = f"메시지 생성 중 오류 발생: {str(e)}"
        logs.append(f"[Step {current_step}] ERROR: {error_msg}")

        return {
            "step": current_step + 1,
            "last_node": "create_product_message_node",
            "current_node": "error_handler",  # 에러 핸들러로 이동
            "error": error_msg,
            "error_details": {
                "node": "create_product_message_node",
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            },
            "logs": logs,
            "status": "failed"
        }


if __name__ == "__main__":
    """
    노드 테스트
    """
    import json
    import sys

    # Windows 인코딩 문제 해결
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    # 테스트 state 생성 (Context 구조 사용 + 사용자 선택)
    test_state: CRMState = {
        "input": "PERSONA_001로 설화수 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘",
        "step": 2,  # recommend_products_node 다음 step
        "logs": [
            "[Step 0] parse_crm_request_node 완료",
            "[Step 1] recommend_products_node 완료"
        ],
        "intermediate": {
            "request": {
                "parsed_request": {
                    "persona_id": "PERSONA_001",
                    "purpose": "신제품 홍보",
                    "product_categories": ["크림"],
                    "brands": ["설화수"],
                    "exclusive_target": None
                }
            },
            "recommendation": {
                "persona_info": {
                    "persona_id": "PERSONA_001",
                    "이름": "김수진",
                    "나이": 28,
                    "성별": "여성",
                    "직업": "마케터",
                    "피부타입": ["건성"],
                    "고민 키워드": ["건조", "주름"],
                    "퍼스널 컬러": "웜톤",
                    "선호 성분": ["세라마이드", "히알루론산"],
                    "기피 성분": ["알코올"],
                    "가치관": ["친환경", "비건"]
                },
                "recommended_products": [
                    {
                        "product_id": "PROD_001",
                        "product_name": "설화수 자음생크림",
                        "brand": "설화수",
                        "product_tag": "스킨케어-크림",
                        "sale_price": 180000,
                        "discount_rate": 0,
                        "rating": 4.8,
                        "review_count": 1523,
                        "skin_type": ["건성", "민감성"],
                        "skin_concerns": ["주름", "탄력"],
                        "preferred_ingredients": ["한방", "자음단"],
                        "vector_search_score": 0.92,
                        "product_page_url": "https://example.com/product/001"
                    }
                ]
            }
        },
        "context": {
            "user_id": "test_user",
            "session_id": "test_session"
        },
        "selected_product_id": "PROD_001"  # 사용자가 선택한 상품 ID
    }

    print("=" * 80)
    print("테스트 입력:")
    print("=" * 80)
    recommended_products = test_state['intermediate']['recommendation']['recommended_products']
    print(f"추천된 상품 수: {len(recommended_products)}개")
    for i, product in enumerate(recommended_products, 1):
        print(f"{i}. {product.get('product_name')} ({product.get('brand')})")
        print(f"   가격: {product.get('sale_price'):,}원")
        print(f"   스코어: {product.get('vector_search_score', 0):.3f}")

    selected_id = test_state.get('selected_product_id')
    if selected_id is not None:
        print(f"\n사용자 선택: 상품 ID {selected_id}")
    else:
        print("\n사용자 선택: 없음")

    print("\n" + "=" * 80)
    print("노드 실행 중...")
    print("=" * 80)

    # 노드 실행
    result = create_product_message_node(test_state)

    print("\n" + "=" * 80)
    print("실행 결과:")
    print("=" * 80)
    print(f"Step: {result.get('step')}")
    print(f"Status: {result.get('status')}")
    print(f"Last Node: {result.get('last_node')}")
    print(f"Next Node: {result.get('current_node')}")

    print("\n" + "=" * 80)
    print("생성된 메시지:")
    print("=" * 80)
    message_context = result.get("intermediate", {}).get("message", {})
    messages = message_context.get("messages", [])
    if messages:
        for i, message in enumerate(messages, 1):
            print(f"\n[메시지 {i}]")
            print(f"상품: {message.get('product_name')} ({message.get('brand')})")
            print(f"제목: {message.get('title')}")
            print(f"\n메시지:")
            print("-" * 80)
            print(message.get('message'))
            print("-" * 80)
            print(f"가격: {message.get('sale_price'):,}원")
            print(f"URL: {message.get('product_url')}")
    else:
        print("생성된 메시지가 없습니다.")

    print("\n" + "=" * 80)
    print("실행 로그:")
    print("=" * 80)
    for log in result.get("logs", []):
        print(log)