from typing import Dict, Any, Optional
from ....core.logging import get_logger
from ....core.langsmith_config import traced
from ....config.settings import settings
import httpx

logger = get_logger("recommend_products")


class PersonaClient:
    def __init__(self):
        self.db_api_url = settings.database_api_url
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """httpx.AsyncClient lazy init (커넥션 풀 재사용)"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http_client

    @traced(name="get_persona_info", run_type="tool")
    async def get_persona_info(self, persona_id: str) -> Dict[str, Any]:
        """페르소나 정보 조회"""
        try:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/personas/get",
                json={"persona_id": persona_id},
            )
            response.raise_for_status()
            api_data = response.json()

            persona_info = {
                "persona_id": api_data.get("persona_id"),
                "이름": api_data.get("name"),
                "나이": api_data.get("age"),
                "성별": api_data.get("gender"),
                "직업": api_data.get("occupation"),
                "피부타입": api_data.get("skin_type", []),
                "고민 키워드": api_data.get("skin_concerns", []),
                "퍼스널 컬러": api_data.get("personal_color"),
                "베이스 호수": api_data.get("shade_number"),
                "메이크업 선호 색상": api_data.get("preferred_colors", []),
                "선호 성분": api_data.get("preferred_ingredients", []),
                "기피 성분": api_data.get("avoided_ingredients", []),
                "선호 향": api_data.get("preferred_scents", []),
                "가치관": api_data.get("values", []),
                "스킨케어 루틴": api_data.get("skincare_routine"),
                "주 활동 환경": api_data.get("main_environment"),
                "선호 제형(텍스처)": api_data.get("preferred_texture", []),
                "반려동물": api_data.get("pets"),
                "수면 시간": f"{api_data.get('avg_sleep_hours')}시간" if api_data.get('avg_sleep_hours') else None,
                "스트레스": api_data.get("stress_level"),
                "디지털 기기 사용": f"하루 {api_data.get('digital_device_usage_time')}시간" if api_data.get('digital_device_usage_time') else None,
                "쇼핑 스타일&예산": api_data.get("shopping_style"),
                "구매 결정 요인": api_data.get("purchase_decision_factors", [])
            }

            logger.info("persona_fetched", persona_id=persona_id, persona_name=persona_info.get("이름"))
            return persona_info

        except Exception as e:
            logger.error("persona_fetch_failed", persona_id=persona_id, error=str(e), exc_info=True)
            raise

    @traced(name="get_existing_product_search_query", run_type="tool")
    async def get_existing_product_search_query(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """DB에서 기존에 생성한 상품 검색 쿼리 조회 (가장 최신 결과 1개)"""
        try:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/product-search-queries/get",
                json={"persona_id": persona_id},
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                return None
            if isinstance(results, list):
                return results[0]
            return results

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("product_search_queries_fetch_failed", persona_id=persona_id, error=str(e))
            raise
        except Exception as e:
            logger.error("product_search_queries_fetch_failed", persona_id=persona_id, error=str(e))
            return None
        
    @traced(name="save_persona", run_type="tool")
    async def save_persona(self, persona_data: Dict[str, Any]) -> str:
        """페르소나 정보를 DB에 저장하고 persona_id 반환"""
        try:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/personas",
                json=persona_data,
            )
            response.raise_for_status()
            result = response.json()
            persona_id = result["persona_id"]
            logger.info("persona_saved", persona_id=persona_id)
            return persona_id

        except httpx.HTTPStatusError as e:
            logger.error("persona_save_failed", status_code=e.response.status_code, error=str(e))
            raise
        except Exception as e:
            logger.error("persona_save_failed", error=str(e))
            raise

    @traced(name="save_product_search_query", run_type="tool")
    async def save_product_search_query(self, persona_id: str, search_queries: Dict[str, Any]) -> Dict[str, int]:
        """생성한 상품 검색 쿼리를 DB에 저장"""
        try:
            data = {
                "persona_id": persona_id,
                **search_queries
            }
            response = await self.http_client.post(
                f"{self.db_api_url}/api/product-search-queries",
                json=data
            )
            response.raise_for_status()
            result = response.json()

            query_ids = {
                "need": result["need"]["query_id"],
                "preference": result["preference"]["query_id"],
                "retrieval": result["retrieval"]["query_id"],
                "persona": result["persona"]["query_id"],
            }
            logger.info("product_search_query_saved", persona_id=persona_id, query_ids=query_ids)
            return query_ids

        except httpx.HTTPStatusError as e:
            logger.error("product_search_query_save_failed", persona_id=persona_id, status_code=e.response.status_code, error=str(e))
            raise
        except Exception as e:
            logger.error("product_search_query_save_failed", persona_id=persona_id, error=str(e))
            raise