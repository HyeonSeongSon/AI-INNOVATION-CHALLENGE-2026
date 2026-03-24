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
        top_k: int = 10
    ):
        """
        combined_vector(KNN) + retrieval_query(BM25) 하이브리드 검색

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
                    "index_name": "product_index_v2",
                    "pipeline_id": "hybrid-minmax-pipeline",
                    "product_ids": product_ids,
                    "query": retrieval_query,
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
        bm25_field: str,
        vector_field: str,
        product_ids: List[str],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """단일 필드 하이브리드 검색 (내부용)"""
        try:
            response = await self.http_client.post(
                f"{self.vector_db_api_url}/api/search/by-field",
                json={
                    "query": query,
                    "bm25_field": bm25_field,
                    "vector_field": vector_field,
                    "product_ids": product_ids,
                    "index_name": "product_index_v2",
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
                bm25_field=bm25_field,
                error=str(e),
                exc_info=True,
            )
            return []

    @traced(name="search_persona_dimensions", run_type="retriever")
    async def search_persona_dimensions(
        self,
        queries: Dict[str, str],
        product_ids: List[str],
        top_k: int = 50,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        페르소나 3개 차원을 독립적으로 병렬 하이브리드 검색

        매핑:
          need       → function_desc  / function_desc_vector
          preference → attribute_desc / attribute_desc_vector
          persona    → target_user    / target_user_vector

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
                bm25_field="function_desc",
                vector_field="function_desc_vector",
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_by_field(
                query=queries["user_preference_query"],
                bm25_field="attribute_desc",
                vector_field="attribute_desc_vector",
                product_ids=product_ids,
                top_k=top_k,
            ),
            self._search_by_field(
                query=queries["persona"],
                bm25_field="target_user",
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

    # 벡터 DB의 한국어 키와 중복되거나 내부용인 DB 필드
    _DB_EXCLUDE_KEYS = {
        "vectordb_id", "product_created_at",
        "product_name", "brand", "product_tag",
        "skin_type", "preferred_ingredients", "avoided_ingredients",
        "preferred_scents", "values", "preferred_colors", "exclusive_product",
    }

    def merge_product_data(self, db_product: Dict[str, Any], vector_product: Dict[str, Any]) -> Dict[str, Any]:
        """
        벡터 DB 데이터를 기반으로 DB의 비중복 필드를 추가해 병합.

        - 벡터 DB: 전체 포함 (_vector 필드, URL 필드 제외)
        - DB: 벡터 DB에 없는 키만 추가 (내부 필드, URL 필드 제외)
        """
        def _is_url_field(key: str) -> bool:
            return "url" in key.lower() or key == "상품이미지"

        vector_clean = {
            k: v for k, v in vector_product.items()
            if "_vector" not in k and not _is_url_field(k)
        }
        db_extra = {
            k: v for k, v in db_product.items()
            if k not in vector_clean and k not in self._DB_EXCLUDE_KEYS and not _is_url_field(k)
        }
        return {**vector_clean, **db_extra}

    async def get_merged_product_info(self, product_id: str) -> Dict[str, Any]:
        """DB + 벡터 DB 상품 정보를 병합하여 반환."""
        vector_products, db_products = await asyncio.gather(
            self.get_products_by_ids([product_id]),
            self.get_products_detail_from_db([product_id]),
        )
        vector_product = vector_products[0] if vector_products else {}
        db_product = db_products[0] if db_products else {}
        return self.merge_product_data(db_product, vector_product)

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

    @traced(name="get_products_by_ids", run_type="retriever")
    async def get_products_by_ids(
        self,
        product_ids: List[str],
        index_name: str = "product_index_v2",
    ) -> List[Dict[str, Any]]:
        """
        product_id 리스트의 상품 정보를 병렬 조회

        Args:
            product_ids: 조회할 상품 ID 리스트 (RRF 순위 순)
            index_name: 검색할 인덱스 이름

        Returns:
            List[Dict]: 상품 문서 리스트 (입력 순서 보장)
        """
        async def _fetch_one(product_id: str) -> Optional[Dict[str, Any]]:
            try:
                response = await self.http_client.get(
                    f"{self.vector_db_api_url}/api/product/{product_id}",
                    params={"index_name": index_name},
                )
                response.raise_for_status()
                return response.json().get("document", {})
            except Exception as e:
                logger.error("get_product_by_id.failed", product_id=product_id, error=str(e))
                return None

        results = await asyncio.gather(*[_fetch_one(pid) for pid in product_ids])
        return [r for r in results if r is not None]