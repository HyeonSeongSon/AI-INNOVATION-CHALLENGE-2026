"""
상품 추천 노드

파싱된 CRM 요청을 기반으로 페르소나 분석 및 상품 추천을 수행하는 노드
"""

import json
from typing import Dict, Any
from ..state import CRMState
from ..services.recommend_products import ProductRecommender
from ....core.logging import AgentLogger


# Recommender 싱글톤 인스턴스 (재사용)
_recommender_instance = None


def get_recommender() -> ProductRecommender:
    """Recommender 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _recommender_instance
    if _recommender_instance is None:
        _recommender_instance = ProductRecommender()
    return _recommender_instance


async def recommend_products_node(state: CRMState) -> Dict[str, Any]:
    """
    파싱된 요청을 기반으로 상품 추천을 수행하는 노드

    Args:
        state: CRMState - 현재 상태

    Returns:
        Dict[str, Any]: 업데이트할 상태

    State 업데이트:
        - intermediate.recommendation.persona_info: 페르소나 정보
        - intermediate.recommendation.analysis_result: 페르소나 분석 결과
        - intermediate.recommendation.analysis_id: 분석 ID
        - intermediate.recommendation.queries: 생성된 검색 쿼리
        - intermediate.recommendation.recommended_products: 추천된 상품 리스트
        - logs: 실행 로그 추가
        - step: step 증가
        - last_node: 현재 노드명 기록
        - current_node: 다음 노드로 업데이트
    """

    logger = AgentLogger(state, node_name="recommend_products_node")
    intermediate = state.get("intermediate", {})

    logger.info(
        "node_started",
        user_message="recommend_products_node 시작",
    )

    try:
        # 1. 파싱된 요청 가져오기 (Context 구조)
        request_context = intermediate.get("request", {})
        parsed_request = request_context.get("parsed_request")
        if not parsed_request:
            raise ValueError("파싱된 요청(parsed_request)이 없습니다.")

        persona_id = parsed_request.get("persona_id")
        brands = parsed_request.get("brands", [])
        product_categories = parsed_request.get("product_categories", [])
        exclusive_target = parsed_request.get("exclusive_target")
        purpose = parsed_request.get("purpose")

        if not persona_id:
            raise ValueError("persona_id가 비어있습니다.")

        logger.info(
            "request_parsed",
            user_message=f"페르소나 ID: {persona_id}",
            persona_id=persona_id,
            brands=brands,
            categories=product_categories,
        )

        # 2. Recommender 가져오기
        recommender = get_recommender()

        # 3. 사용자 입력 가져오기
        user_input = state.get("input", "")

        # 4. 페르소나 정보 조회
        with logger.track_duration("get_persona_info", user_message="페르소나 정보 조회 중..."):
            persona_info = await recommender.get_persona_info(persona_id)

        logger.info(
            "persona_info_fetched",
            user_message=f"페르소나 정보 조회 완료: {persona_info.get('이름')}",
            persona_name=persona_info.get("이름"),
        )

        # 5. 기존 분석 결과 확인
        logger.info(
            "checking_existing_analysis",
            user_message="기존 분석 결과 확인 중...",
        )
        existing_analysis = await recommender.get_existing_analysis(persona_id)

        analysis_result = None
        analysis_id = None

        if existing_analysis:
            analysis_id = existing_analysis['analysis_id']
            logger.info(
                "existing_analysis_found",
                user_message=f"기존 분석 발견 (ID: {analysis_id})",
                analysis_id=analysis_id,
            )
            try:
                analysis_result = json.loads(existing_analysis['analysis_result'])
            except json.JSONDecodeError:
                logger.warning(
                    "analysis_parse_failed",
                    user_message="기존 분석 파싱 실패, 새로 생성",
                )
                analysis_result = None
        else:
            logger.info(
                "no_existing_analysis",
                user_message="기존 분석 없음, 새로 생성",
            )

        # 6. 분석 결과가 없으면 새로 생성
        if not analysis_result:
            with logger.track_duration("persona_analysis", user_message="페르소나 분석 수행 중..."):
                analysis_result = await recommender.recommend_persona(
                    user_input=user_input,
                    persona_id=persona_id
                )

            # DB에 저장
            with logger.track_duration("save_analysis", user_message="분석 결과 DB 저장 중..."):
                analysis_id = await recommender.save_analysis_result(
                    persona_id=persona_id,
                    analysis_result=analysis_result
                )

            logger.info(
                "analysis_saved",
                user_message=f"분석 저장 완료 (ID: {analysis_id})",
                analysis_id=analysis_id,
            )

        # 7. 멀티 쿼리 생성
        with logger.track_duration("multi_query_generation", user_message="멀티 쿼리 생성 중..."):
            queries = await recommender.generate_multi_queries(
                user_input=user_input,
                analysis_result=analysis_result,
                product_categories=product_categories
            )

        logger.info(
            "queries_generated",
            user_message=f"쿼리 생성 완료: {len(queries)}개",
            query_count=len(queries),
        )

        # 8. 쿼리 DB 저장
        with logger.track_duration("save_queries", user_message="쿼리 DB 저장 중..."):
            await recommender.save_search_queries(
                analysis_id=analysis_id,
                queries=queries
            )

        # 9. 멀티 쿼리로 벡터 검색
        with logger.track_duration("vector_search", user_message="멀티 쿼리 검색 수행 중..."):
            search_results = await recommender.search_with_multi_queries(
                queries=queries,
                brands=brands if brands else None,
                product_categories=product_categories if product_categories else None,
                exclusive_target=exclusive_target,
                top_k=5
            )

        # Context 구조로 저장
        if "recommendation" not in intermediate:
            intermediate["recommendation"] = {}

        if not search_results:
            logger.info(
                "no_search_results",
                user_message="검색 결과 없음",
            )
            intermediate["recommendation"]["recommended_products"] = []
        else:
            # 10. 상품 데이터 병합
            with logger.track_duration("merge_products", user_message="상품 데이터 병합 중..."):
                all_products = await recommender.get_filtered_products(
                    brands=brands if brands else None,
                    product_categories=product_categories if product_categories else None,
                    exclusive_target=exclusive_target
                )

                merged_products = recommender.merge_product_data(
                    search_results=search_results,
                    all_products=all_products
                )

            # 상위 3개만 선택
            top_3_products = merged_products[:3]
            logger.info(
                "products_recommended",
                user_message=f"상품 추천 완료: 상위 {len(top_3_products)}개 (전체 {len(merged_products)}개)",
                top_count=len(top_3_products),
                total_count=len(merged_products),
            )

            # Context 구조로 결과 저장
            intermediate["recommendation"]["recommended_products"] = top_3_products

        # 분석 관련 정보도 Context 구조로 저장
        intermediate["recommendation"]["persona_info"] = persona_info
        intermediate["recommendation"]["analysis_result"] = analysis_result
        intermediate["recommendation"]["analysis_id"] = analysis_id
        intermediate["recommendation"]["queries"] = queries

        # 상태 업데이트
        return {
            "step": state.get("step", 0) + 1,
            "last_node": "recommend_products_node",
            "current_node": "create_message_node",  # 다음 노드
            "intermediate": intermediate,
            "logs": logger.get_user_logs(),
            "status": "running"
        }

    except Exception as e:
        # 에러 처리
        error_msg = f"상품 추천 중 오류 발생: {str(e)}"
        logger.error(
            "node_failed",
            user_message=f"ERROR: {error_msg}",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )

        return {
            "step": state.get("step", 0) + 1,
            "last_node": "recommend_products_node",
            "current_node": "error_handler",  # 에러 핸들러로 이동
            "error": error_msg,
            "error_details": {
                "node": "recommend_products_node",
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
    from pprint import pprint

    # 테스트 state 생성 (Context 구조 사용)
    test_state: CRMState = {
        "input": "PERSONA_001로 설화수 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘",
        "step": 1,  # parse_crm_request_node 다음 step
        "logs": ["[Step 0] parse_crm_request_node 완료"],
        "intermediate": {
            "request": {
                "parsed_request": {
                    "persona_id": "PERSONA_001",
                    "purpose": "신제품 홍보",
                    "product_categories": ["크림"],
                    "brands": ["설화수"],
                    "exclusive_target": None
                }
            }
        },
        "context": {
            "user_id": "test_user",
            "session_id": "test_session"
        }
    }

    print("=" * 80)
    print("테스트 입력:")
    print("=" * 80)
    pprint(test_state["intermediate"]["request"]["parsed_request"], width=80, indent=2)

    print("\n" + "=" * 80)
    print("노드 실행 중...")
    print("=" * 80)

    # 노드 실행
    result = recommend_products_node(test_state)

    print("\n" + "=" * 80)
    print("실행 결과:")
    print("=" * 80)
    print(f"Step: {result.get('step')}")
    print(f"Status: {result.get('status')}")
    print(f"Last Node: {result.get('last_node')}")
    print(f"Next Node: {result.get('current_node')}")

    print("\n" + "=" * 80)
    print("추천된 상품:")
    print("=" * 80)
    recommendation = result.get("intermediate", {}).get("recommendation", {})
    recommended_products = recommendation.get("recommended_products", [])
    if recommended_products:
        for i, product in enumerate(recommended_products, 1):
            print(f"\n{i}. {product.get('product_name')} ({product.get('brand')})")
            print(f"   가격: {product.get('sale_price'):,}원")
            print(f"   스코어: {product.get('vector_search_score', 0):.3f}")
    else:
        print("추천된 상품이 없습니다.")

    print("\n" + "=" * 80)
    print("실행 로그:")
    print("=" * 80)
    for log in result.get("logs", []):
        print(log)
