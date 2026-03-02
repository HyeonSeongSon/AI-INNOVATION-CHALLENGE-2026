"""
상품 메시지 생성 노드

추천된 상품들에 대해 목적별 맞춤 메시지를 생성하는 노드
"""

import os
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from ..state import CRMState
from ....core.llm_factory import get_llm
from ..services.create_product_message import ProductMessageGenerator
from ....core.logging import AgentLogger


# Generator 인스턴스 
_generator = ProductMessageGenerator()


async def create_product_message_node(state: CRMState, config: RunnableConfig) -> Dict[str, Any]:
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

    logger = AgentLogger(state, node_name="create_product_message_node")
    intermediate = state.get("intermediate", {})

    logger.info(
        "node_started",
        user_message="create_product_message_node 시작",
    )

    try:
        # 1. 필요한 데이터 가져오기 (Context 구조)
        request_context = intermediate.get("request", {})
        recommendation_context = intermediate.get("recommendation", {})

        parsed_request = request_context.get("parsed_request")
        persona_info = recommendation_context.get("persona_info")
        recommended_products = recommendation_context.get("recommended_products", [])

        # 사용자가 선택한 상품 ID 가져오기 (intermediate.hitl에 저장된 interrupt 결과)
        selected_product_id = intermediate.get("hitl", {}).get("product_selection")

        # Context 구조 초기화
        if "message" not in intermediate:
            intermediate["message"] = {}

        if not recommended_products:
            logger.info(
                "no_products",
                user_message="추천된 상품이 없습니다.",
            )
            intermediate["message"]["messages"] = []

            return {
                "step": state.get("step", 0) + 1,
                "last_node": "create_product_message_node",
                "current_node": "end",  # 상품이 없으면 종료
                "intermediate": intermediate,
                "logs": logger.get_user_logs(),
                "status": "completed"
            }

        if not persona_info:
            raise ValueError("페르소나 정보가 없습니다.")

        if not parsed_request:
            raise ValueError("파싱된 요청 정보가 없습니다.")

        # 사용자 선택 확인 (필수)
        if selected_product_id is None:
            logger.error(
                "no_product_selected",
                user_message="ERROR: 사용자가 상품을 선택하지 않았습니다.",
            )
            raise ValueError("사용자가 상품을 선택하지 않았습니다. selected_product_id가 필요합니다.")

        # 선택된 상품 ID로 상품 찾기
        selected_product = None
        for product in recommended_products:
            if product.get("product_id") == selected_product_id:
                selected_product = product
                break

        if selected_product is None:
            logger.error(
                "product_not_found",
                user_message=f"ERROR: 상품 ID '{selected_product_id}'를 찾을 수 없습니다.",
                selected_product_id=selected_product_id,
            )
            raise ValueError(f"상품 ID '{selected_product_id}'를 찾을 수 없습니다.")

        logger.info(
            "product_selected",
            user_message=f"사용자 선택 상품: {selected_product_id} - {selected_product.get('product_name')}",
            selected_product_id=selected_product_id,
            product_name=selected_product.get("product_name"),
        )

        # 목적 가져오기
        purpose = parsed_request.get("purpose", "브랜드/제품 소개")
        logger.info(
            "message_purpose",
            user_message=f"메시지 생성 목적: {purpose}",
            purpose=purpose,
        )

        # 품질 검사 피드백 읽기 (재시도 시 활용 — 가장 최근 실패 이력에서 읽음)
        quality_check_context = intermediate.get("quality_check", {})
        regeneration_history = quality_check_context.get("regeneration_history", [])
        retry_count = quality_check_context.get("retry_count", 0)
        if regeneration_history:
            last_attempt = regeneration_history[-1]
            quality_feedback = last_attempt.get("feedback")
            failed_msg = last_attempt.get("failed_message", {})
            previous_message = f"제목: {failed_msg.get('title', '')}\n메시지: {failed_msg.get('message', '')}"

            # 마지막 시도가 semantic/rule 실패(LLM judge 미도달)인 경우,
            # 이전 시도의 LLM judge 피드백을 함께 전달
            if not last_attempt.get("scores"):
                for prev in reversed(regeneration_history[:-1]):
                    if prev.get("scores", {}).get("feedback"):
                        quality_feedback = (
                            f"{quality_feedback}\n\n"
                            f"[이전 LLM 평가 피드백]\n{prev['scores']['feedback']}"
                        )
                        break
        else:
            quality_feedback = None
            previous_message = None

        if quality_feedback:
            logger.info(
                "retrying_with_feedback",
                user_message=f"품질 검사 피드백 반영하여 메시지 재생성 (시도 {retry_count + 1}/3)",
                retry_count=retry_count,
            )

        # 2. config에서 모델명 읽기 후 LLM 생성
        model_name = config.get("configurable", {}).get("model", os.getenv("CHATGPT_MODEL_NAME"))
        llm = get_llm(model_name, temperature=0.7)

        # 3. 선택된 상품에 대해 메시지 생성
        messages = []
        product_name = selected_product.get("product_name", "알 수 없음")

        with logger.track_duration("message_generation", user_message=f"메시지 생성 중: {product_name}"):
            message_result = await _generator.generate_message(
                product=selected_product,
                persona_info=persona_info,
                purpose=purpose,
                quality_feedback=quality_feedback,
                previous_message=previous_message,
                llm=llm,
            )

        if message_result.get("success"):
            # 생성 성공
            message_data = {
                "product_id": selected_product.get("product_id"),
                "product_name": selected_product.get("product_name"),
                "brand": selected_product.get("brand"),
                "title": message_result.get("title", ""),
                "message": message_result.get("message", ""),
                "purpose": purpose,
                "vector_search_score": selected_product.get("vector_search_score", 0),
                "product_url": selected_product.get("product_page_url", ""),
                "sale_price": selected_product.get("sale_price", 0)
            }
            messages.append(message_data)
            logger.info(
                "message_created",
                user_message="메시지 생성 완료",
                product_id=selected_product.get("product_id"),
            )
        else:
            # 생성 실패
            error_msg = message_result.get("error", "알 수 없는 오류")
            logger.warning(
                "message_generation_failed",
                user_message=f"메시지 생성 실패: {error_msg}",
                error=error_msg,
            )

        # 4. Context 구조로 결과 저장
        logger.info(
            "node_completed",
            user_message=f"전체 메시지 생성 완료: {len(messages)}개",
            message_count=len(messages),
        )
        intermediate["message"]["selected_product"] = selected_product
        intermediate["message"]["messages"] = messages
        intermediate["message"]["product_document_summary"] = message_result.get("product_document_summary")

        # 상태 업데이트
        return {
            "step": state.get("step", 0) + 1,
            "last_node": "create_product_message_node",
            "current_node": "end",  # 메시지 생성 완료 후 종료
            "intermediate": intermediate,
            "logs": logger.get_user_logs(),
            "status": "completed"
        }

    except Exception as e:
        # 에러 처리
        error_msg = f"메시지 생성 중 오류 발생: {str(e)}"
        logger.error(
            "node_failed",
            user_message=f"ERROR: {error_msg}",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )

        return {
            "step": state.get("step", 0) + 1,
            "last_node": "create_product_message_node",
            "current_node": "error_handler",  # 에러 핸들러로 이동
            "error": error_msg,
            "error_details": {
                "node": "create_product_message_node",
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            },
            "logs": logger.get_user_logs(),
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
            },
            # interrupt 결과는 intermediate.hitl에 저장 (state 최상위 필드 X)
            "hitl": {
                "product_selection": "PROD_001"  # 사용자가 선택한 상품 ID
            }
        },
        "context": {
            "user_id": "test_user",
            "session_id": "test_session"
        },
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

    selected_id = test_state.get('intermediate', {}).get('hitl', {}).get('product_selection')
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
