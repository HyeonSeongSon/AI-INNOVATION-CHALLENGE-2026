"""
페르소나 기반 상품 추천 Tool (Tool Calling 방식)
다단계×다차원 분석 + 멀티 쿼리 검색
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
import json
from .recommend_products import ProductRecommender


@tool
def recommend_products_persona(
    persona_id: str,
    user_input: str,
    brands: Optional[List[str]] = None,
    product_categories: Optional[List[str]] = None,
    exclusive_target: Optional[str] = None,
    top_k: int = 5
) -> str:
    """페르소나 기반 다단계×다차원 분석으로 제품을 추천합니다.

    이 도구는 페르소나 정보를 심층 분석하여 최적의 제품을 추천합니다.

    **작동 방식:**
    1. 페르소나 정보 조회
    2. 다단계×다차원 분석 수행
       - 다단계: 기본 프로필, 라이프스타일 패턴, 뷰티 니즈, 상황별 니즈, 개선 목표
       - 다차원: 피부 과학, 성분, 라이프스타일, 감성/가치관, 색조, 가격/가성비, 사용 편의성, 안전성/리스크
    3. 멀티 쿼리 생성 (3~5개의 다각도 검색 쿼리)
    4. 벡터 검색 수행 (각 쿼리로 검색 후 중복 제거)
    5. 최고 스코어 상품 반환

    Args:
        persona_id: 페르소나 ID (필수)
        user_input: 사용자 요청 텍스트 (필수, 예: "겨울철 건조한 피부에 좋은 크림 추천해줘")
        brands: 브랜드 필터 (선택, 예: ["설화수", "헤라"])
        product_categories: 상품 카테고리 필터 (선택, 예: ["스킨케어-크림", "메이크업-립스틱"])
        exclusive_target: 특정 대상 전용 제품 (선택, 예: "임산부전용")
        top_k: 각 쿼리당 검색할 상품 수 (기본값: 5)

    Returns:
        추천 제품 리스트 (JSON 문자열):
        {
            "persona_info": {...},
            "analysis_result": {
                "multi_level_analysis": {...},
                "multi_dimensional_analysis": {...}
            },
            "queries": ["쿼리1", "쿼리2", "쿼리3"],
            "products": [
                {
                    "product_id": "PROD001",
                    "product_name": "설화수 자음생크림",
                    "brand": "설화수",
                    "sale_price": 150000,
                    "vector_search_score": 0.95,
                    ...
                }
            ],
            "count": 3
        }

    언제 사용하나요?
    - 페르소나 정보를 심층 분석하여 맞춤형 제품 추천이 필요할 때
    - 사용자의 요청에 맞는 제품을 다각도로 검색해야 할 때
    - CRM 메시지 생성을 위해 최적의 제품을 선별해야 할 때
    """
    print(f"\n[recommend_products_persona Tool 시작]")
    print(f"  - persona_id: {persona_id}")
    print(f"  - user_input: {user_input}")
    print(f"  - brands: {brands}")
    print(f"  - product_categories: {product_categories}")
    print(f"  - top_k: {top_k}")

    try:
        recommender = ProductRecommender()

        # 1. 페르소나 정보 조회
        print("[1단계] 페르소나 정보 조회 중...")
        persona_info = recommender.get_persona_info(persona_id)

        # 2. DB에서 기존 분석 결과 조회
        print("[2단계] 기존 분석 결과 확인 중...")
        existing_analysis = recommender.get_existing_analysis(persona_id)

        if existing_analysis:
            print(f"  → 기존 분석 결과 발견 (analysis_id: {existing_analysis['analysis_id']})")
            analysis_result_text = existing_analysis['analysis_result']
            analysis_id = existing_analysis['analysis_id']
            # JSON 파싱
            try:
                analysis_result = json.loads(analysis_result_text)
            except json.JSONDecodeError:
                print("[WARNING] 기존 분석 결과 파싱 실패, 새로 생성합니다.")
                analysis_result = None
        else:
            print("  → 기존 분석 결과 없음, 새로 생성합니다.")
            analysis_result = None
            analysis_id = None

        # 3. 분석 결과가 없으면 새로 생성
        if not analysis_result:
            print("[3단계] 페르소나 분석 수행 중...")
            analysis_result = recommender.recommend_persona(
                user_input=user_input,
                persona_id=persona_id
            )

            # DB에 저장
            print("[4단계] 분석 결과 DB 저장 중...")
            analysis_id = recommender.save_analysis_result(
                persona_id=persona_id,
                analysis_result=analysis_result
            )
            print(f"  → 저장 완료 (analysis_id: {analysis_id})")

        # 5. 멀티 쿼리 생성
        print("[5단계] 멀티 쿼리 생성 중...")
        queries = recommender.generate_multi_queries(
            user_input=user_input,
            analysis_result=analysis_result,
            product_categories=product_categories
        )

        # 6. 생성된 쿼리를 DB에 저장
        print("[6단계] 쿼리 DB 저장 중...")
        recommender.save_search_queries(
            analysis_id=analysis_id,
            queries=queries
        )

        # 7. 멀티 쿼리로 벡터 검색 (내부에서 필터링 수행)
        print("[7단계] 멀티 쿼리 검색 중...")
        search_results = recommender.search_with_multi_queries(
            queries=queries,
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target,
            top_k=top_k
        )

        if not search_results:
            return json.dumps({
                "error": "검색 결과가 없습니다.",
                "products": []
            }, ensure_ascii=False)

        # 8. 상품 데이터 병합을 위해 필터링된 상품 목록 가져오기
        print("[8단계] 상품 데이터 병합 중...")
        all_products = recommender.get_filtered_products(
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target
        )

        merged_products = recommender.merge_product_data(
            search_results=search_results,
            all_products=all_products
        )

        # 9. 결과 반환 (JSON 문자열)
        result = {
            "persona_info": persona_info,
            "analysis_result": analysis_result,
            "analysis_id": analysis_id,
            "queries": queries,
            "products": merged_products,
            "count": len(merged_products)
        }

        print(f"[recommend_products_persona Tool 완료] {len(merged_products)}개 상품 추천")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        error_result = {
            "error": str(e),
            "products": []
        }
        print(f"[ERROR] recommend_products_persona Tool 실패: {e}")
        return json.dumps(error_result, ensure_ascii=False)
