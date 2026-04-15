from typing import Optional, List, Dict, Any
from ....core.langsmith_config import traced
from ....core.logging import get_logger
from ....config.settings import settings
import httpx
import asyncio

logger = get_logger("recommend_products")

class ProductClient:
    def __init__(self):
        self.db_api_url = settings.database_api_url
        self.vector_db_api_url = settings.opensearch_api_url
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """httpx.AsyncClient lazy init (커넥션 풀 재사용)"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http_client

    @traced(name="get_filtered_products", run_type="tool")
    async def get_filtered_products(
        self,
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None,
        exclusive_target: Optional[str] = None,
        avoided_ingredients: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """필터 조건에 맞는 상품 조회"""
        filters = {}
        if brands:
            filters["brands"] = brands
        if product_categories:
            filters["product_categories"] = product_categories
        if exclusive_target:
            filters["exclusive_target"] = exclusive_target
        if avoided_ingredients:
            filters["avoided_ingredients"] = avoided_ingredients

        try:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/products/filter",
                json=filters,
            )
            response.raise_for_status()
            products = response.json()
            logger.info("products_filtered", product_count=len(products), filters=filters)
            return products

        except Exception as e:
            logger.error("products_filter_failed", error=str(e), exc_info=True)
            raise
        
    @traced(name="search_combined_vector", run_type="retriever")
    async def search_by_combined_vector(
        self,
        retrieval_query: str,
        product_ids: List[str],
        top_k: int = 10,
    ):
        """
        combined_vector(KNN) + search_tags/search_phrases(BM25) 하이브리드 검색

        BM25: search_tags + search_phrases (검색 최적화 필드)
        Vector: combined_vector

        Args:
            retrieval_query: 검색 쿼리 텍스트
            product_ids: 검색 범위를 제한할 상품 ID 리스트
            top_k: 반환할 최대 결과 수
        """
        if not product_ids:
            logger.warning("search_by_combined_vector.no_product_ids")
            return []

        try:
            response = await self.http_client.post(
                f"{self.vector_db_api_url}/api/search/combined",
                json={
                    "index_name": "product_index_v3",
                    "pipeline_id": "hybrid-minmax-pipeline",
                    "product_ids": product_ids,
                    "query": retrieval_query,
                    "bm25_fields": ["search_tags.text", "search_phrases"],
                    "vector_field": "combined_vector",
                    "top_k": top_k,
                },
            )
            response.raise_for_status()
            api_response = response.json()

            if isinstance(api_response, dict) and "results" in api_response:
                return api_response["results"]
            return api_response

        except Exception as e:
            logger.error("search_by_combined_vector.failed", error=str(e), exc_info=True)
            return []

    @traced(name="search_opensearch", run_type="retriever")
    async def search_with_multi_queries(
        self,
        queries: List[str],
        product_ids: List[str],
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        멀티 쿼리로 벡터 검색 수행 및 결과 병합 (asyncio.gather 병렬 실행)

        Args:
            queries: 검색 쿼리 리스트
            product_ids: 검색 범위를 제한할 상품 ID 리스트 (get_filtered_products 결과)
            top_k: 쿼리당 반환할 최대 결과 수
        """
        if not product_ids:
            logger.warning("no_filtered_products")
            return []

        all_query_results = await asyncio.gather(
            *[self.search_by_combined_vector(q, product_ids, top_k) for q in queries]
        )
        return all_query_results

    async def _search_by_field(
        self,
        query: str,
        bm25_fields: List[str],
        vector_field: str,
        product_ids: List[str],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """다중 BM25 필드 + 벡터 하이브리드 검색 (내부용)"""
        try:
            response = await self.http_client.post(
                f"{self.vector_db_api_url}/api/search/by-field",
                json={
                    "query": query,
                    "bm25_fields": bm25_fields,
                    "vector_field": vector_field,
                    "product_ids": product_ids,
                    "index_name": "product_index_v3",
                    "pipeline_id": "hybrid-minmax-pipeline",
                    "top_k": top_k,
                },
            )
            response.raise_for_status()
            api_response = response.json()
            return api_response.get("results", [])
        except Exception as e:
            logger.error(
                "search_by_field.failed",
                bm25_fields=bm25_fields,
                error=str(e),
                exc_info=True,
            )
            return []

    @traced(name="search_persona_dimensions", run_type="retriever")
    async def search_persona_dimensions(
        self,
        queries: Dict[str, str],
        product_ids: List[str],
        top_k: int = 100,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        페르소나 3개 차원을 독립적으로 병렬 하이브리드 검색

        매핑:
          need       → function_tags + function_desc   / function_desc_vector
          preference → attribute_tags + attribute_desc / combined_vector
          persona    → target_tags + target_user       / target_user_vector

        Args:
            queries: get_product_search_queries 반환값
            product_ids: product_retriever로 추려진 상품 ID 리스트
            top_k: 차원별 반환 결과 수

        Returns:
            {
                "need":       [{"score": float, "product_id": str}, ...],
                "preference": [...],
                "persona":    [...],
            }
        """
        if not product_ids:
            logger.warning("search_persona_dimensions.no_product_ids")
            return {"need": [], "preference": [], "persona": []}

        need_result, preference_result, persona_result = await asyncio.gather(
            self._search_by_field(
                query=queries["user_need_query"],
                bm25_fields=["function_tags.text", "function_desc"],
                vector_field="function_desc_vector",
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_by_field(
                query=queries["user_preference_query"],
                bm25_fields=["attribute_tags.text", "attribute_desc"],
                vector_field="combined_vector",
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_by_field(
                query=queries["persona"],
                bm25_fields=["target_tags.text", "target_user"],
                vector_field="target_user_vector",
                product_ids=product_ids,
                top_k=top_k,
            ),
        )

        logger.info(
            "search_persona_dimensions.done",
            need_count=len(need_result),
            preference_count=len(preference_result),
            persona_count=len(persona_result),
        )

        return {
            "need": need_result,
            "preference": preference_result,
            "persona": persona_result,
        }

    _V4_INDICES = {
        "combined":       "product_v4_combined",
        "function_desc":  "product_v4_function_desc",
        "attribute_desc": "product_v4_attribute_desc",
        "target_user":    "product_v4_target_user",
        "spec_feature":   "product_v4_spec_feature",
    }

    async def _search_multivector(
        self,
        query: str,
        index_name: str,
        product_ids: List[str],
        top_k: int = 100,
        aggregation: str = "max",
    ) -> List[Dict[str, Any]]:
        """POST /api/search/multivector 호출 (내부용)"""
        try:
            response = await self.http_client.post(
                f"{self.vector_db_api_url}/api/search/multivector",
                json={
                    "query": query,
                    "index_name": index_name,
                    "product_ids": product_ids,
                    "top_k": top_k,
                    "aggregation": aggregation,
                },
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            logger.error(
                "search_multivector.failed",
                index_name=index_name,
                error=str(e),
                exc_info=True,
            )
            return []

    @traced(name="search_by_multivector_combined", run_type="retriever")
    async def search_by_multivector_combined(
        self,
        retrieval_query: str,
        product_ids: List[str],
        top_k: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Step 2 (Recall): combined + spec_feature 인덱스 병렬 검색 후 product_id별 max 머지

        Args:
            retrieval_query: 검색 쿼리
            product_ids: 필터링된 상품 ID 리스트
            top_k: 반환할 최대 상품 수

        Returns:
            [{"product_id": str, "score": float}, ...] 내림차순
        """
        if not product_ids:
            logger.warning("search_by_multivector_combined.no_product_ids")
            return []

        combined_result, spec_result = await asyncio.gather(
            self._search_multivector(
                query=retrieval_query,
                index_name=self._V4_INDICES["combined"],
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_multivector(
                query=retrieval_query,
                index_name=self._V4_INDICES["spec_feature"],
                product_ids=product_ids,
                top_k=top_k,
            ),
        )

        # product_id별 max score 머지
        score_map: Dict[str, float] = {}
        for item in combined_result + spec_result:
            pid = item.get("product_id")
            score = item.get("score", 0.0)
            if pid and score > score_map.get(pid, 0.0):
                score_map[pid] = score

        merged = sorted(score_map.items(), key=lambda x: x[1], reverse=True)[:top_k]
        logger.info("search_by_multivector_combined.done", result_count=len(merged))
        return [{"product_id": pid, "score": score} for pid, score in merged]

    @traced(name="search_persona_dimensions_multivector", run_type="retriever")
    async def search_persona_dimensions_multivector(
        self,
        queries: Dict[str, str],
        product_ids: List[str],
        top_k: int = 100,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Step 3 (Rerank): function_desc / attribute_desc / target_user 인덱스 병렬 검색

        Args:
            queries: get_product_search_queries 반환값
            product_ids: Step 2 결과 상품 ID 리스트
            top_k: 차원별 반환 결과 수

        Returns:
            {"need": [...], "preference": [...], "persona": [...]}  ← 기존 포맷 동일
        """
        if not product_ids:
            logger.warning("search_persona_dimensions_multivector.no_product_ids")
            return {"need": [], "preference": [], "persona": []}

        need_result, preference_result, persona_result = await asyncio.gather(
            self._search_multivector(
                query=queries["user_need_query"],
                index_name=self._V4_INDICES["function_desc"],
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_multivector(
                query=queries["user_preference_query"],
                index_name=self._V4_INDICES["attribute_desc"],
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_multivector(
                query=queries["persona"],
                index_name=self._V4_INDICES["target_user"],
                product_ids=product_ids,
                top_k=top_k,
            ),
        )

        logger.info(
            "search_persona_dimensions_multivector.done",
            need_count=len(need_result),
            preference_count=len(preference_result),
            persona_count=len(persona_result),
        )

        return {
            "need": need_result,
            "preference": preference_result,
            "persona": persona_result,
        }

    def flatten_product_data(self, db_product: Dict[str, Any]) -> Dict[str, Any]:
        """
        정형 DB 응답에서 product_details를 최상위 필드로 펼쳐 반환.

        - 최상위 DB 필드가 베이스
        - product_details 필드가 우선 (같은 키면 product_details 값)
        - _vector 필드 및 URL 필드 제외
        """
        def _is_url_field(key: str) -> bool:
            return "url" in key.lower() or key == "상품이미지"

        product_details = db_product.get("product_details") or {}

        db_base = {
            k: v for k, v in db_product.items()
            if k != "product_details" and "_vector" not in k and not _is_url_field(k)
        }
        details_clean = {
            k: v for k, v in product_details.items()
            if "_vector" not in k and not _is_url_field(k)
        }
        return {**db_base, **details_clean}

    async def get_merged_product_info(self, product_id: str) -> Dict[str, Any]:
        """정형 DB 상품 정보를 조회하여 product_details를 펼쳐 반환."""
        db_products = await self.get_products_detail_from_db([product_id])
        db_product = db_products[0] if db_products else {}
        return self.flatten_product_data(db_product)

    @traced(name="get_products_detail_from_db", run_type="tool")
    async def get_products_detail_from_db(
        self,
        product_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """정형 DB에서 product_id 리스트로 상품 상세 정보 병렬 조회 (가격, 할인율 등)"""
        async def _fetch_one(product_id: str) -> Optional[Dict[str, Any]]:
            try:
                response = await self.http_client.get(
                    f"{self.db_api_url}/api/products/{product_id}",
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error("get_products_detail_from_db.failed", product_id=product_id, error=str(e))
                return None

        results = await asyncio.gather(*[_fetch_one(pid) for pid in product_ids])
        return [r for r in results if r is not None]

    async def get_products_by_ids(self, product_ids: List[str]) -> List[Dict[str, Any]]:
        """get_products_detail_from_db의 alias."""
        return await self.get_products_detail_from_db(product_ids)