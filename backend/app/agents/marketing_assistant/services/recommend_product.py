from typing import Dict, List, Optional
from ....config.settings import settings
from .generate_persona_and_query import generate_search_query
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
        self.llm = get_llm(settings.chatgpt_model_name, temperature=0.3)
    
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
            raw_queries = await generate_search_query(persona_info, self.llm)

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
            sub_tags: Optional[List[str]],
            avoided_ingredients: Optional[List[str]]
        ):
        # 레벨 1: brands + sub_tags + avoided_ingredients(EXCLUDE)
        filtered_products = await _product_client.get_filtered_products(
            brands=brands if brands else None,
            product_categories=sub_tags if sub_tags else None,
            avoided_ingredients=avoided_ingredients if avoided_ingredients else None,
        )

        # 레벨 2: brands 제거 (sub_tags + EXCLUDE)
        if len(filtered_products) < settings.min_filtered_products and brands:
            logger.warning(
                "filter_fallback_level2",
                current_count=len(filtered_products),
            )
            filtered_products = await _product_client.get_filtered_products(
                brands=None,
                product_categories=sub_tags if sub_tags else None,
                avoided_ingredients=avoided_ingredients if avoided_ingredients else None,
            )

        # 레벨 3: sub_tags도 제거 (EXCLUDE만)
        if len(filtered_products) < settings.min_filtered_products and sub_tags:
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
            sub_tags: Optional[List[str]],
            avoided_ingredients: Optional[List[str]],
            allowed_product_ids: Optional[List[str]] = None,
        ):

        if allowed_product_ids is not None:
            filtered_product_ids = allowed_product_ids
        else:
            filtered_product_ids = await self.filtered_products(
                brands=brands if brands else None,
                sub_tags=sub_tags if sub_tags else None,
                avoided_ingredients=avoided_ingredients if avoided_ingredients else None
            )

        retrieval_result = await _product_client.search_by_multivector_combined(retrieval_query, filtered_product_ids, top_k=100)
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
        results = await _product_client.search_persona_dimensions_multivector(
            queries=queries,
            product_ids=retrieval_result_ids,
        )
        logger.info("get_product_documents.done")
        return results

    # 기본 가중치 (카테고리 미지정 시 사용) — 균등 가중치로 안전하게 유지
    # eval 결과: need=1.2 default는 메이크업·헤어·바디케어 등 다수 카테고리를 hurt함
    _DIMENSION_WEIGHTS: Dict[str, float] = {
        "retrieval": 1.0,
        "need":      1.2,
        "preference":1.1,
        "persona":   1.0,
    }

    # 카테고리별 가중치 오버라이드
    _CATEGORY_WEIGHTS: Dict[str, Dict[str, float]] = {
        # 스킨케어 — need 우위 또는 need·preference 균형이 효과적인 카테고리
        "스킨&토너":     {"retrieval": 1.0, "need": 1.2, "preference": 1.0, "persona": 0.8},
        "크림":          {"retrieval": 1.0, "need": 1.1, "preference": 1.1, "persona": 0.8},
        "로션&에멀젼":   {"retrieval": 1.0, "need": 1.1, "preference": 1.1, "persona": 0.8},
        # 마스크&팩 — need 소폭 강화 (균등보다 낫고 old weight보다 안전한 중간값)
        "마스크&팩":     {"retrieval": 1.0, "need": 1.1, "preference": 1.0, "persona": 0.9},
        # 메이크업 — 기능 need보다 개인 취향(preference)이 구매 결정 핵심
        "파운데이션":    {"retrieval": 1.0, "need": 0.9, "preference": 1.2, "persona": 1.0},
        # 헬스/웰니스 — 기능적 need 매칭이 핵심
        "이너뷰티":      {"retrieval": 1.0, "need": 1.2, "preference": 1.0, "persona": 0.8},
        "슬리밍":        {"retrieval": 1.0, "need": 1.2, "preference": 1.0, "persona": 0.8},
        "영양보충":      {"retrieval": 1.0, "need": 1.2, "preference": 1.0, "persona": 0.8},
        # 가전/기기류 — retrieval·need 균형 강화, persona 감소
        "헤어드라이기":  {"retrieval": 1.2, "need": 1.1, "preference": 1.0, "persona": 0.7},
        "고데기":        {"retrieval": 1.2, "need": 1.1, "preference": 1.0, "persona": 0.7},
        "청소기":        {"retrieval": 1.2, "need": 1.1, "preference": 1.0, "persona": 0.7},
        "전동마사지기":  {"retrieval": 1.3, "need": 1.2, "preference": 1.0, "persona": 0.6},
        # 생활용품
        "수저/용기류":   {"retrieval": 1.2, "need": 1.1, "preference": 1.0, "persona": 0.7},
    }

    @staticmethod
    def _apply_rrf(
        dimension_results: Dict,
        weights: Optional[Dict[str, float]] = None,
        k: int = 15,
    ) -> List[tuple]:
        """
        Reciprocal Rank Fusion으로 3개 차원 결과 합산 (차원별 가중치 적용)

        RRF score = Σ w_i / (k + rank_i)

        Args:
            dimension_results: {"need": [...], "preference": [...], "persona": [...]}
            weights: 차원별 가중치. None이면 _DIMENSION_WEIGHTS(기본값) 사용
            k: RRF 상수. 낮을수록 상위 순위 차별화 강화 (기본값 10, 표준 RRF는 60)

        Returns:
            [(product_id, rrf_score), ...] 내림차순
        """
        weights = weights or ProductRecommender._DIMENSION_WEIGHTS
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
        product_tag: Optional[str] = None,
    ) -> List[Dict]:
        """
        3차원 하이브리드 검색 + RRF → 상위 top_n개 상품 정보 반환

        Args:
            queries: get_product_search_queries 반환값
            retrieval_result_ids: product_retriever 결과 상품 ID 리스트
            top_n: 최종 반환할 상품 수 (기본값 3)
            product_tag: 카테고리 태그. 카테고리별 가중치 적용에 사용

        Returns:
            List[Dict]: RRF 순위 기준 상위 top_n개 상품 전체 정보
        """
        # 3차원 병렬 하이브리드 검색
        dimension_results = await self.get_product_documents(queries, retrieval_result_ids)

        # 1차 retrieval 순위를 4번째 차원으로 추가 (추가 API 호출 없음)
        dimension_results["retrieval"] = [
            {"product_id": pid} for pid in retrieval_result_ids
        ]

        # 카테고리별 가중치 선택 (미지정 또는 매핑 없으면 기본값)
        weights = ProductRecommender._CATEGORY_WEIGHTS.get(product_tag) if product_tag else None

        logger.info(
            "recommend.weights_selected",
            product_tag=product_tag,
            weights=weights or ProductRecommender._DIMENSION_WEIGHTS,
        )

        # RRF로 최종 순위 결정
        ranked = self._apply_rrf(dimension_results, weights=weights)
        top_ranked = ranked[:top_n]
        top_ids = [pid for pid, _ in top_ranked]
        score_map = {pid: round(score, 4) for pid, score in top_ranked}

        logger.info(
            "recommend.rrf_done",
            top_ids=top_ids,
            rrf_scores=score_map,
        )

        # 상품 상세 정보 병렬 조회
        products = await _product_client.get_products_detail_from_db(top_ids)

        # RRF 순위 보장 + 스코어 삽입
        id_to_product = {p.get("product_id"): p for p in products}
        return [
            {**id_to_product[pid], "rrf_score": score_map[pid]}
            for pid in top_ids
            if pid in id_to_product
        ]