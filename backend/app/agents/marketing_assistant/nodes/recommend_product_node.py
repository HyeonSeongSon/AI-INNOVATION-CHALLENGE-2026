from ..services.recommend_product import ProductRecommender
from ..services.parse_crm_request import MultiValueParser
from langchain_core.runnables import RunnableConfig
from ..state import MarketingAssistantState
from ....core.logging import AgentLogger
from ....config.settings import settings
from ....core.llm_factory import get_llm
import json

_parser = MultiValueParser()
_recommender = ProductRecommender()

async def recommend_product_node(state: MarketingAssistantState, config: RunnableConfig):
    logger = AgentLogger(state, node_name="recommend_product_node")

    logger.info(
        "node_started",
        user_message="상품 추천 시작",
    )

    messages = state.get("messages")
    parser_llm = get_llm(settings.parser_model_name, temperature=0.7)

    # messages[-1]은 AnyMessage 객체이므로 .content로 문자열 추출
    parsed_json = await _parser.parse(messages[-1].content, parser_llm)
    parsed_data = json.loads(parsed_json)

    logger.info(
        "parse_completed",
        user_message=f"요청 파싱 완료 (persona: {parsed_data.get('persona_id')})",
        persona_id=parsed_data.get("persona_id"),
        brands=parsed_data.get("brands"),
        categories=parsed_data.get("product_categories"),
    )

    # 페르소나 기반 검색 쿼리 조회 (Dict: user_need_query, user_preference_query, retrieval, persona)
    search_queries = await _recommender.get_product_search_queries(
        persona_id=parsed_data.get("persona_id")
    )

    logger.info(
        "search_queries_ready",
        user_message="검색 쿼리 준비 완료",
        query_keys=list(search_queries.keys()),
    )

    # retrieval 쿼리(str)만 추출해서 벡터 검색 후보 상품 ID 수집
    retrieval_product_ids = await _recommender.product_retriever(
        retrieval_query=search_queries["retrieval"],
        brands=parsed_data.get("brands") or None,
        product_tag=parsed_data.get("product_categories") or None,
        avoided_ingredients=None,
    )

    logger.info(
        "retrieval_done",
        user_message=f"후보 상품 {len(retrieval_product_ids)}개 검색 완료",
        product_count=len(retrieval_product_ids),
    )

    # 3차원 하이브리드 검색 + RRF로 최종 추천 상품 선정
    recommended_products = await _recommender.recommend(search_queries, retrieval_product_ids)

    logger.info(
        "recommend_done",
        user_message=f"최종 추천 상품 {len(recommended_products)}개 선정 완료",
        product_count=len(recommended_products),
    )

    return {
        "search_queries": search_queries,
        "recommended_products": recommended_products,
        "logs": logger.get_user_logs(),
    }







