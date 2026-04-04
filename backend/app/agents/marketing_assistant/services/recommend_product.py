from typing import Dict, List, Optional
from ....config.settings import settings
from .generate_product_search_query_from_persona import generate_product_search_query_from_persona
from .persona_client import PersonaClient
from .product_client import ProductClient
from ....core.llm_factory import get_llm
from ....core.logging import get_logger


_product_client = ProductClient()
_persona_client = PersonaClient()
logger = get_logger(__name__)

class ProductRecommender:
    def __init__(self):
        self.vector_db_api_url = settings.opensearch_api_url
        self.db_api_url = settings.database_api_url
        self.llm = get_llm(settings.chatgpt_model_name, temperature=0)
    
    async def get_product_search_queries(self, persona_id):
        logger.info("product_search_queries.start", persona_id=persona_id)
        
        # 기존 상품 검색 쿼리 조회
        existing_product_search_queries = await _persona_client.get_existing_product_search_query(persona_id)

        if existing_product_search_queries:
            # 기존 검색 쿼리 사용
            logger.info("product_search_queries.cache_hit", persona_id=persona_id)
            search_queries = {
                "user_need_query": existing_product_search_queries['need']['text'],
                "user_preference_query": existing_product_search_queries['preference']['text'],
                "retrieval": existing_product_search_queries['retrieval']['text'],
                "persona": existing_product_search_queries['persona']['text']
            }
        else:
            # 기존 검색 쿼리 없으면 상품 검색 쿼리 생성
            logger.info("product_search_queries.generating", persona_id=persona_id)
            persona_info = await _persona_client.get_persona_info(persona_id)
            raw_queries = await generate_product_search_query_from_persona(self.llm, persona_info)

            # DB저장
            await _persona_client.save_product_search_query(persona_id, raw_queries)
            logger.info("product_search_queries.saved", persona_id=persona_id)

            search_queries = {
                "user_need_query": raw_queries["need"],
                "user_preference_query": raw_queries["preference"],
                "retrieval": raw_queries["retrieval"],
                "persona": raw_queries["persona"],
            }

        logger.info("product_search_queries.done", persona_id=persona_id, query_keys=list(search_queries.keys()))
        return search_queries
    
    async def filtered_products(
            self,
            brands: Optional[str],
            products: Optional[List[str]],
            avoided_ingredients: Optional[List[str]]
        ):
        # 레벨 1: brands + categories + avoided_ingredients(EXCLUDE)
        filtered_products = await _product_client.get_filtered_products(
            brands=brands if brands else None,
            product_categories=products if products else None,
            avoided_ingredients=avoided_ingredients if avoided_ingredients else None,
        )

        # 레벨 2: brands 제거 (카테고리 + EXCLUDE)
        if len(filtered_products) < settings.min_filtered_products and brands:
            logger.warning(
                "filter_fallback_level2",
                current_count=len(filtered_products),
            )
            filtered_products = await _product_client.get_filtered_products(
                brands=None,
                product_categories=products if products else None,
                avoided_ingredients=avoided_ingredients if avoided_ingredients else None,
            )

        # 레벨 3: 카테고리도 제거 (EXCLUDE만)
        if len(filtered_products) < settings.min_filtered_products and products:
            logger.warning(
                "filter_fallback_level3",
                current_count=len(filtered_products),
            )
            filtered_products = await _product_client.get_filtered_products(
                brands=None,
                product_categories=None,
                avoided_ingredients=avoided_ingredients if avoided_ingredients else None,
            )

        # 레벨 4: 필터 전체 제거 (전체 상품)
        if len(filtered_products) < settings.min_filtered_products:
            logger.warning(
                "filter_fallback_level4",
                current_count=len(filtered_products),
            )
            filtered_products = await _product_client.get_filtered_products()

        product_ids = [p["product_id"] for p in filtered_products]
        return product_ids
    
    async def product_retriever(
            self,
            retrieval_query: str, 
            brands: Optional[List[str]],
            product_tag: Optional[List[str]],
            avoided_ingredients: Optional[List[str]]
        ):

        filtered_product_ids = await self.filtered_products(
            brands=brands if brands else None,
            products=product_tag if product_tag else None,
            avoided_ingredients=avoided_ingredients if avoided_ingredients else None
        )

        retrieval_result = await _product_client.search_by_combined_vector(retrieval_query, filtered_product_ids, top_k=100)
        retrieval_result_ids = [p['product_id'] for p in retrieval_result]
        
        return retrieval_result_ids
    
    async def get_product_documents(
            self,
            queries: Dict,
            retrieval_result_ids: List[str]
    ) -> Dict:
        """
        product_retriever로 추려진 상품을 대상으로 페르소나 3개 차원 하이브리드 검색 (병렬)

        Args:
            queries: get_product_search_queries 반환값
                - user_need_query   → function_desc 필드
                - user_preference_query → attribute_desc 필드
                - persona           → target_user 필드
            retrieval_result_ids: product_retriever 결과 상품 ID 리스트

        Returns:
            {
                "need":       [{"score": float, "product_id": str}, ...],
                "preference": [...],
                "persona":    [...],
            }
        """
        logger.info(
            "get_product_documents.start",
            product_count=len(retrieval_result_ids),
        )
        results = await _product_client.search_persona_dimensions(
            queries=queries,
            product_ids=retrieval_result_ids,
        )
        logger.info("get_product_documents.done")
        return results

    _DIMENSION_WEIGHTS: Dict[str, float] = {
        "retrieval": 1.2,   # 1차 retrieval 순위 — 보조 타이브레이커
        "need": 1.5,        # 기능 니즈 — 가장 직접적인 매칭 신호
        "preference": 0.6,  # 선호/속성 — 두 번째 중요 신호
        "persona": 0.3,     # 페르소나 유사도 — 보조 신호
    }

    @staticmethod
    def _apply_rrf(dimension_results: Dict, k: int = 15) -> List[tuple]:
        """
        Reciprocal Rank Fusion으로 3개 차원 결과 합산 (차원별 가중치 적용)

        RRF score = Σ w_i / (k + rank_i)
        각 차원(need, preference, persona)에 차별화된 가중치를 적용해 최종 순위 결정

        Args:
            dimension_results: {"need": [...], "preference": [...], "persona": [...]}
            k: RRF 상수 (기본값 20)

        Returns:
            [(product_id, rrf_score), ...] 내림차순
        """
        weights = ProductRecommender._DIMENSION_WEIGHTS
        rrf_scores: Dict[str, float] = {}
        for dim_name, results in dimension_results.items():
            w = weights.get(dim_name, 1.0)
            for rank, item in enumerate(results, start=1):
                pid = item["product_id"]
                rrf_scores[pid] = rrf_scores.get(pid, 0.0) + w * (1.0 / (k + rank))
        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    async def recommend(
        self,
        queries: Dict,
        retrieval_result_ids: List[str],
        top_n: int = 3,
    ) -> List[Dict]:
        """
        3차원 하이브리드 검색 + RRF → 상위 top_n개 상품 정보 반환

        Args:
            queries: get_product_search_queries 반환값
            retrieval_result_ids: product_retriever 결과 상품 ID 리스트
            top_n: 최종 반환할 상품 수 (기본값 3)

        Returns:
            List[Dict]: RRF 순위 기준 상위 top_n개 상품 전체 정보
        """
        # 3차원 병렬 하이브리드 검색
        dimension_results = await self.get_product_documents(queries, retrieval_result_ids)

        # 1차 retrieval 순위를 4번째 차원으로 추가 (추가 API 호출 없음)
        dimension_results["retrieval"] = [
            {"product_id": pid} for pid in retrieval_result_ids
        ]

        # RRF로 최종 순위 결정
        ranked = self._apply_rrf(dimension_results)
        top_ranked = ranked[:top_n]
        top_ids = [pid for pid, _ in top_ranked]
        score_map = {pid: round(score, 4) for pid, score in top_ranked}

        logger.info(
            "recommend.rrf_done",
            top_ids=top_ids,
            rrf_scores=score_map,
        )

        # 상품 상세 정보 병렬 조회
        products = await _product_client.get_products_by_ids(top_ids)

        # RRF 순위 보장 + 스코어 삽입
        id_to_product = {p.get("product_id"): p for p in products}
        return [
            {**id_to_product[pid], "rrf_score": score_map[pid]}
            for pid in top_ids
            if pid in id_to_product
        ]