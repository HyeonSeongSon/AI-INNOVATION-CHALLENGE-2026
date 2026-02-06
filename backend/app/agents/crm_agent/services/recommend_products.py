from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from ..prompts.crm_recommend_products import build_persona_info_analysis_prompt, build_multil_query_generate_prompt
import os
import json
import requests

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


class ProductRecommender:
    """상품 추천 로직"""
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        chat_gpt_model_name = os.getenv("CHATGPT_MODEL_NAME")
        self.vector_db_api_url = os.getenv("OPENSEARCH_API_URL")
        self.db_api_url = os.getenv("DATABASE_API_URL")

        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model=chat_gpt_model_name,
            temperature=0.7,
            api_key=api_key,
            request_timeout=30
        )

    def get_persona_info(self, persona_id: str) -> Dict[str, Any]:
        """페르소나 정보 조회"""
        try:
            response = requests.post(
                f"{self.db_api_url}/api/personas/get",
                json={"persona_id": persona_id},
                timeout=10
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

            print(f"[INFO] 페르소나 정보 조회 성공: {persona_info.get('이름')}")
            return persona_info

        except Exception as e:
            print(f"[ERROR] 페르소나 정보 조회 실패: {e}")
            raise

    def get_existing_analysis(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """DB에서 기존 분석 결과 조회 (가장 최신 결과 1개)"""
        try:
            response = requests.post(
                f"{self.db_api_url}/api/analysis-results/get",
                json={"persona_id": persona_id},
                timeout=10
            )
            response.raise_for_status()
            results = response.json()

            if results and len(results) > 0:
                # 가장 최신 결과 반환 (이미 시간순 정렬되어 있음)
                return results[0]
            return None

        except requests.exceptions.HTTPException as e:
            if e.response.status_code == 404:
                return None
            print(f"[ERROR] 분석 결과 조회 실패: {e}")
            raise
        except Exception as e:
            print(f"[ERROR] 분석 결과 조회 실패: {e}")
            return None

    def save_analysis_result(self, persona_id: str, analysis_result: Dict[str, Any]) -> int:
        """분석 결과를 DB에 저장"""
        try:
            # JSON을 문자열로 변환
            analysis_result_text = json.dumps(analysis_result, ensure_ascii=False)

            response = requests.post(
                f"{self.db_api_url}/api/analysis-results",
                json={
                    "persona_id": persona_id,
                    "analysis_result": analysis_result_text
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            # analysis_id 반환
            return result.get("analysis_id")

        except Exception as e:
            print(f"[ERROR] 분석 결과 저장 실패: {e}")
            raise

    def save_search_queries(self, analysis_id: int, queries: List[str]) -> None:
        """검색 쿼리를 DB에 저장"""
        try:
            for query in queries:
                response = requests.post(
                    f"{self.db_api_url}/api/search-queries",
                    json={
                        "analysis_id": analysis_id,
                        "search_query": query
                    },
                    timeout=10
                )
                response.raise_for_status()

            print(f"[INFO] {len(queries)}개 쿼리 저장 완료")

        except Exception as e:
            print(f"[ERROR] 쿼리 저장 실패: {e}")
            raise

    def get_filtered_products(
        self,
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None,
        exclusive_target: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """필터 조건에 맞는 상품 조회"""
        filters = {}
        if brands:
            filters["brands"] = brands
        if product_categories:
            filters["product_categories"] = product_categories
        if exclusive_target:
            filters["exclusive_target"] = exclusive_target

        try:
            response = requests.post(
                f"{self.db_api_url}/api/products/filter",
                json=filters,
                timeout=10
            )
            response.raise_for_status()
            products = response.json()
            print(f"[INFO] 필터링된 상품 수: {len(products)}개")
            return products

        except Exception as e:
            print(f"[ERROR] 상품 필터링 실패: {e}")
            raise
        
    def recommend_persona(self, user_input: str, persona_id: str) -> Dict[str, Any]:
        """
        페르소나 기반 다단계 × 다차원 분석

        Args:
            user_input: 사용자 입력 텍스트 (예: "겨울철 건조한 피부에 좋은 크림 추천해줘")
            persona_id: 페르소나 ID

        Returns:
            Dict[str, Any]: 다단계 × 다차원 분석 결과
            {
                "multi_level_analysis": {
                    "basic_profile": {...},
                    "lifestyle_pattern": {...},
                    "beauty_needs": {...},
                    "situational_needs": {...},
                    "improvement_goals": {...}
                },
                "multi_dimensional_analysis": {
                    "skin_science": {...},
                    "ingredients": {...},
                    "lifestyle": {...},
                    "values_emotion": {...},
                    "color_makeup": {...},
                    "price_value": {...},
                    "usability": {...},
                    "safety_risk": {...}
                }
            }
        """
        # 1. 페르소나 정보 가져오기
        persona_info = self.get_persona_info(persona_id)

        # 2. 프롬프트 생성
        prompt = self._build_analysis_prompt(user_input, persona_info)

        # 3. LLM 호출하여 분석 수행
        try:
            response = self.llm.invoke(prompt)
        except Exception as e:
            print(f"[ERROR] LLM 호출 실패 (페르소나 분석): {e}")
            return {
                "multi_level_analysis": {},
                "multi_dimensional_analysis": {}
            }

        # 4. 응답 파싱 (JSON 형태로 받음)
        try:
            result = json.loads(response.content)
            print(f"[INFO] 페르소나 분석 완료")
            print(f"  - 다단계 분석: {len(result.get('multi_level_analysis', {}))}개 레벨")
            print(f"  - 다차원 분석: {len(result.get('multi_dimensional_analysis', {}))}개 차원")
            return result
        except json.JSONDecodeError:
            print(f"[ERROR] LLM 응답 파싱 실패: {response.content}")
            return {
                "multi_level_analysis": {},
                "multi_dimensional_analysis": {}
            }

    def _build_analysis_prompt(self, user_input: str, persona_info: Dict[str, Any]) -> str:
        """
        다단계 × 다차원 분석을 위한 프롬프트 구성
        """
        persona_info = json.dumps(persona_info, ensure_ascii=False, indent=2)
        prompt = build_persona_info_analysis_prompt(user_input, persona_info)
        return prompt

    def generate_multi_queries(
        self,
        user_input: str,
        analysis_result: Dict[str, Any],
        product_categories: Optional[List[str]] = None
    ) -> List[str]:
        """
        분석 결과를 기반으로 멀티 쿼리 생성

        Args:
            user_input: 사용자 입력 텍스트
            analysis_result: recommend_persona 함수의 분석 결과
            product_categories: 제품 카테고리 리스트 (선택, 예: ["스킨케어-크림", "메이크업-립스틱"])

        Returns:
            List[str]: 3~5개의 다각도 검색 쿼리
        """
        # 프롬프트 생성
        prompt = build_multil_query_generate_prompt(user_input, analysis_result, product_categories)

        # LLM 호출하여 멀티 쿼리 생성
        try:
            response = self.llm.invoke(prompt)
        except Exception as e:
            print(f"[ERROR] LLM 호출 실패 (멀티 쿼리 생성): {e}")
            return [user_input]

        # 응답 파싱
        try:
            result = json.loads(response.content)
            queries = result.get("queries", [])
            print(f"[INFO] 생성된 쿼리 수: {len(queries)}개")
            for i, q in enumerate(queries, 1):
                print(f"  {i}. {q}")
            return queries
        except json.JSONDecodeError:
            print(f"[ERROR] LLM 응답 파싱 실패: {response.content}")
            return [user_input]

    def search_with_multi_queries(
        self,
        queries: List[str],
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None,
        exclusive_target: Optional[str] = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        멀티 쿼리로 벡터 검색 수행 및 결과 병합

        Args:
            queries: 검색 쿼리 리스트 (3~5개)
            brands: 브랜드 필터 (선택)
            product_categories: 상품 카테고리 필터 (선택)
            exclusive_target: 타겟 필터 (선택)
            top_k: 각 쿼리당 가져올 상품 수

        Returns:
            List[Dict[str, Any]]: 중복 제거된 검색 결과 (스코어 높은 순)
            [
                {
                    "product_id": "PROD001",
                    "score": 0.95,
                    ...
                }
            ]
        """
        # 1. 필터링된 상품 조회
        filtered_products = self.get_filtered_products(
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target
        )
        product_ids = [p["product_id"] for p in filtered_products]

        if not product_ids:
            print("[WARNING] 필터링 결과 상품이 없습니다.")
            return []

        all_results = []

        # 2. 각 쿼리로 검색 수행
        for i, query in enumerate(queries, 1):
            print(f"[INFO] 쿼리 {i}/{len(queries)} 검색 중: {query}")
            try:
                response = requests.post(
                    f"{self.vector_db_api_url}/api/search/product-ids",
                    json={
                        "index_name": "product_index",
                        "pipeline_id": "hybrid-minmax-pipeline",
                        "product_ids": product_ids,
                        "query": query,
                        "top_k": top_k
                    },
                    timeout=15
                )
                response.raise_for_status()
                api_response = response.json()

                # 응답 형식 처리
                if isinstance(api_response, dict) and "results" in api_response:
                    results = api_response["results"]
                else:
                    results = api_response

                # 결과를 전체 리스트에 추가
                all_results.extend(results)
                print(f"  → {len(results)}개 상품 검색됨")

            except Exception as e:
                print(f"[ERROR] 쿼리 {i} 검색 실패: {e}")
                continue

        # 중복 제거: product_id별로 최고 스코어만 유지
        product_score_map = {}
        for result in all_results:
            product_id = result.get("product_id")
            score = result.get("score", 0)

            if product_id not in product_score_map:
                product_score_map[product_id] = result
            else:
                # 기존 스코어보다 높으면 교체
                if score > product_score_map[product_id].get("score", 0):
                    product_score_map[product_id] = result

        # 스코어 높은 순으로 정렬
        merged_results = sorted(
            product_score_map.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        print(f"[INFO] 멀티 쿼리 검색 완료")
        print(f"  - 전체 검색 결과: {len(all_results)}개")
        print(f"  - 중복 제거 후: {len(merged_results)}개")

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
                merged.append(product_data)

        print(f"[INFO] 상품 데이터 병합 완료: {len(merged)}개")
        return merged