from typing import Dict, Any, List, Optional
from langchain_core.language_models import BaseChatModel
from dotenv import load_dotenv
from ..prompts.crm_recommend_products import build_persona_info_analysis_prompt, build_multi_query_generate_prompt
from ....core.logging import get_logger
from ....core.langsmith_config import traced
import os
import json
import httpx
import asyncio

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"), override=True)

logger = get_logger("recommend_products")

RRF_K = int(os.getenv("RRF_K", "60"))  # Reciprocal Rank Fusion 상수 (표준값 60)

class ProductRecommender:
    """상품 추천 로직"""
    def __init__(self):
        self.vector_db_api_url = os.getenv("OPENSEARCH_API_URL")
        self.db_api_url = os.getenv("DATABASE_API_URL")
        self._http_client: Optional[httpx.AsyncClient] = None
        logger.info("recommender_initialized")

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

    @traced(name="get_existing_analysis", run_type="tool")
    async def get_existing_analysis(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """DB에서 기존 분석 결과 조회 (가장 최신 결과 1개)"""
        try:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/analysis-results/get",
                json={"persona_id": persona_id},
            )
            response.raise_for_status()
            results = response.json()

            if results and len(results) > 0:
                return results[0]
            return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("analysis_fetch_failed", persona_id=persona_id, error=str(e))
            raise
        except Exception as e:
            logger.error("analysis_fetch_failed", persona_id=persona_id, error=str(e))
            return None

    @traced(name="save_analysis_result", run_type="tool")
    async def save_analysis_result(self, persona_id: str, analysis_result: Dict[str, Any]) -> int:
        """분석 결과를 DB에 저장"""
        try:
            analysis_result_text = json.dumps(analysis_result, ensure_ascii=False)

            response = await self.http_client.post(
                f"{self.db_api_url}/api/analysis-results",
                json={
                    "persona_id": persona_id,
                    "analysis_result": analysis_result_text
                },
            )
            response.raise_for_status()
            result = response.json()

            return result.get("analysis_id")

        except Exception as e:
            logger.error("analysis_save_failed", persona_id=persona_id, error=str(e), exc_info=True)
            raise

    @traced(name="save_search_queries", run_type="tool")
    async def save_search_queries(self, analysis_id: int, queries: List[str]) -> None:
        """검색 쿼리를 DB에 저장 (asyncio.gather 병렬 실행)"""
        async def _save_single(query: str) -> None:
            response = await self.http_client.post(
                f"{self.db_api_url}/api/search-queries",
                json={
                    "analysis_id": analysis_id,
                    "search_query": query
                },
            )
            response.raise_for_status()

        results = await asyncio.gather(
            *[_save_single(q) for q in queries],
            return_exceptions=True
        )

        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.warning(
                "some_queries_save_failed",
                analysis_id=analysis_id,
                failed_count=len(exceptions),
                total_count=len(queries),
            )
            if len(exceptions) == len(queries):
                raise exceptions[0]
        else:
            logger.info("queries_saved", analysis_id=analysis_id, query_count=len(queries))

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

    @traced(name="recommend_persona", run_type="chain")
    async def recommend_persona(self, persona_id: str, llm: BaseChatModel) -> Dict[str, Any]:
        """
        페르소나 기반 다단계 × 다차원 분석

        Args:
            persona_id: 페르소나 ID

        Returns:
            Dict[str, Any]: 다단계 × 다차원 분석 결과
        """
        # 1. 페르소나 정보 가져오기
        persona_info = await self.get_persona_info(persona_id)

        # 2. 프롬프트 생성
        prompt = self._build_analysis_prompt(persona_info)

        # 3. LLM 호출하여 분석 수행
        try:
            response = await llm.ainvoke(prompt)
        except Exception as e:
            logger.error("llm_persona_analysis_failed", persona_id=persona_id, error=str(e), exc_info=True)
            return {
                "multi_level_analysis": {},
                "multi_dimensional_analysis": {}
            }

        # 4. 응답 파싱 (JSON 형태로 받음)
        try:
            result = json.loads(response.content)
            logger.info(
                "persona_analysis_completed",
                persona_id=persona_id,
                multi_level_count=len(result.get("multi_level_analysis", {})),
                multi_dimensional_count=len(result.get("multi_dimensional_analysis", {})),
            )
            return result
        except json.JSONDecodeError:
            logger.error("llm_response_parse_failed", persona_id=persona_id, response_preview=str(response.content)[:200])
            return {
                "multi_level_analysis": {},
                "multi_dimensional_analysis": {}
            }

    def _extract_populated_fields(self, persona_info: Dict[str, Any]) -> Dict[str, bool]:
        """
        PersonaInfo dict에서 실제 데이터가 있는 필드와 빈 필드를 분류.
        LLM 프롬프트에 전달하여 추론 범위를 명시하는 데 사용됨.
        """
        list_fields = [
            "피부타입", "고민 키워드", "메이크업 선호 색상",
            "선호 성분", "기피 성분", "선호 향", "가치관",
            "선호 제형(텍스처)", "구매 결정 요인",
        ]
        str_fields = [
            "퍼스널 컬러", "베이스 호수", "스킨케어 루틴",
            "주 활동 환경", "반려동물", "수면 시간",
            "스트레스", "디지털 기기 사용", "쇼핑 스타일&예산",
        ]
        result: Dict[str, bool] = {}
        for f in list_fields:
            result[f] = bool(persona_info.get(f))  # 빈 리스트 [] → False
        for f in str_fields:
            val = persona_info.get(f)
            result[f] = bool(val and str(val).strip())  # None / "" → False
        return result

    def _build_analysis_prompt(self, persona_info: Dict[str, Any]) -> str:
        """
        다단계 × 다차원 분석을 위한 프롬프트 구성
        """
        populated_fields = self._extract_populated_fields(persona_info)
        persona_info_str = json.dumps(persona_info, ensure_ascii=False, indent=2)
        prompt = build_persona_info_analysis_prompt(persona_info_str, populated_fields)
        return prompt

    @traced(name="generate_multi_queries", run_type="chain")
    async def generate_multi_queries(
        self,
        user_input: str,
        analysis_result: Dict[str, Any],
        product_categories: Optional[List[str]] = None,
        llm: Optional[BaseChatModel] = None,
        persona_info: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        분석 결과를 기반으로 멀티 쿼리 생성

        Args:
            user_input: 사용자 입력 텍스트
            analysis_result: recommend_persona 함수의 분석 결과(페르소나 분석 정보)
            product_categories: 제품 카테고리 리스트 (선택)
            persona_info: 원본 페르소나 정보 (퍼스널컬러, 고민키워드 등을 쿼리에 직접 반영)

        Returns:
            List[str]: 3~5개의 다각도 검색 쿼리
        """
        # 프롬프트 생성
        prompt = build_multi_query_generate_prompt(user_input, analysis_result, product_categories, persona_info)

        # LLM 호출하여 멀티 쿼리 생성
        try:
            response = await llm.ainvoke(prompt)
        except Exception as e:
            logger.error("llm_multi_query_failed", error=str(e), exc_info=True)
            return [user_input]

        # 응답 파싱
        try:
            result = json.loads(response.content)
            queries = result.get("queries", [])
            logger.info("multi_queries_generated", query_count=len(queries), queries=queries)
            return queries
        except json.JSONDecodeError:
            logger.error("llm_response_parse_failed", response_preview=str(response.content)[:200])
            return [user_input]

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

        # 2. 단일 쿼리 실행 코루틴
        async def search_single(query: str, query_index: int) -> List[Dict[str, Any]]:
            logger.info("query_searching", query_index=query_index, total_queries=len(queries), query=query)
            try:
                response = await self.http_client.post(
                    f"{self.vector_db_api_url}/api/search/product-ids",
                    json={
                        "index_name": "product_index",
                        "pipeline_id": "hybrid-minmax-pipeline",
                        "product_ids": product_ids,
                        "query": query,
                        "top_k": top_k
                    },
                )
                response.raise_for_status()
                api_response = response.json()

                # 응답 형식 처리
                if isinstance(api_response, dict) and "results" in api_response:
                    results = api_response["results"]
                else:
                    results = api_response

                logger.info("query_results", query_index=query_index, result_count=len(results))
                return results

            except Exception as e:
                logger.error("query_search_failed", query_index=query_index, query=query, error=str(e))
                return []

        # 3. asyncio.gather로 모든 쿼리 동시 실행
        all_query_results = await asyncio.gather(
            *[search_single(q, i) for i, q in enumerate(queries, 1)]
        )

        # 4. RRF(Reciprocal Rank Fusion)로 결과 병합
        # 각 쿼리 결과에서 rank(1-indexed)를 기반으로 1/(k+rank) 누적
        total_raw = 0
        product_rrf_map: Dict[str, Any] = {}

        for query_results in all_query_results:
            total_raw += len(query_results)
            for rank, result in enumerate(query_results, 1):
                product_id = result.get("product_id")
                raw_score = result.get("score", 0)
                rrf_contribution = 1.0 / (RRF_K + rank)

                if product_id not in product_rrf_map:
                    product_rrf_map[product_id] = {
                        "product_id": product_id,
                        "score": 0.0,
                        "appearance_count": 0,
                        "max_vector_score": 0.0,
                    }

                product_rrf_map[product_id]["score"] += rrf_contribution
                product_rrf_map[product_id]["appearance_count"] += 1
                product_rrf_map[product_id]["max_vector_score"] = max(
                    product_rrf_map[product_id]["max_vector_score"],
                    raw_score
                )

        # RRF 스코어 높은 순으로 정렬
        merged_results = sorted(
            product_rrf_map.values(),
            key=lambda x: x["score"],
            reverse=True
        )

        logger.info(
            "multi_query_search_completed",
            total_raw=total_raw,
            deduplicated=len(merged_results),
        )

        return merged_results

    def merge_product_data(
        self,
        search_results: List[Dict[str, Any]],
        all_products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """검색 결과와 전체 상품 데이터 병합"""
        product_map = {p["product_id"]: p for p in all_products}

        merged = []
        for result in search_results:
            product_id = result.get("product_id")
            if product_id in product_map:
                product_data = product_map[product_id].copy()
                product_data["vector_search_score"] = result.get("score")
                product_data["query_appearance_count"] = result.get("appearance_count", 0)
                product_data["max_vector_score"] = result.get("max_vector_score", 0.0)
                merged.append(product_data)

        logger.info("products_merged", merged_count=len(merged))
        return merged
