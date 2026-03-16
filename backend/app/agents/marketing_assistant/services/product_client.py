from typing import Optional, List, Dict, Any
from ....core.langsmith_config import traced
from ....core.logging import get_logger
from ....config.settings import settings
import httpx

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