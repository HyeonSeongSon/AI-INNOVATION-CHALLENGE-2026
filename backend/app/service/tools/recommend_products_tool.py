"""
상품 추천 Tool (Tool Calling 방식)
LLM이 호출하는 단순 Tool - 워크플로우 없음
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import json
import requests

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


class ProductRecommender:
    """상품 추천 로직"""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0.7,
            api_key=api_key
        )

    def get_persona_info(self, persona_id: str) -> Dict[str, Any]:
        """페르소나 정보 조회"""
        try:
            response = requests.post(
                "http://localhost:8000/api/personas/get",
                json={"persona_id": persona_id}
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
                "http://localhost:8000/api/products/filter",
                json=filters
            )
            response.raise_for_status()
            products = response.json()
            print(f"[INFO] 필터링된 상품 수: {len(products)}개")
            return products

        except Exception as e:
            print(f"[ERROR] 상품 필터링 실패: {e}")
            raise

    def create_search_query(
        self,
        persona_info: Dict[str, Any],
        purpose: Optional[str] = None,
        brands: Optional[List[str]] = None,
        product_categories: Optional[List[str]] = None
    ) -> str:
        """검색 쿼리 생성"""
        persona_sections = []
        if persona_info.get('이름'):
            persona_sections.append(f"- 이름: {persona_info['이름']}")
        if persona_info.get('피부타입'):
            persona_sections.append(f"- 피부타입: {persona_info['피부타입']}")
        if persona_info.get('고민 키워드'):
            persona_sections.append(f"- 피부 고민: {', '.join(persona_info['고민 키워드'])}")
        if persona_info.get('선호 성분'):
            persona_sections.append(f"- 선호 성분: {', '.join(persona_info['선호 성분'])}")

        persona_text = "## 페르소나 정보\n" + "\n".join(persona_sections)

        campaign_sections = []
        if purpose:
            campaign_sections.append(f"- 목적: {purpose}")
        if brands:
            campaign_sections.append(f"- 브랜드: {', '.join(brands)}")
        if product_categories:
            campaign_sections.append(f"- 타겟 제품군: {', '.join(product_categories)}")

        campaign_info = ""
        if campaign_sections:
            campaign_info = "\n## 캠페인 정보\n" + "\n".join(campaign_sections)

        prompt = f"""
{campaign_info}
{persona_text}

위 캠페인 정보(목적, 브랜드, 타겟 제품군)를 바탕으로 페르소나의 특성을 참고하여 제품 검색 쿼리를 한 문장으로 작성하세요.

**작성 규칙**:
1. 캠페인의 목적, 브랜드, 타겟 제품군을 반드시 포함하세요.
2. 페르소나의 피부 타입, 고민, 선호 성분 중 캠페인과 관련된 내용을 선택적으로 포함하세요.
3. 반드시 한 문장으로만 작성하세요.
4. 추가 설명, 제목, 부연 설명 없이 검색 쿼리 문장만 출력하세요.
"""

        try:
            response = self.llm.invoke(prompt)
            search_query = response.content
            print(f"[INFO] 생성된 검색 쿼리: {search_query}")
            return search_query
        except Exception as e:
            print(f"[ERROR] 검색 쿼리 생성 실패: {e}")
            return "추천 상품"

    def search_products(
        self,
        product_ids: List[str],
        search_query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """벡터 검색 실행"""
        try:
            response = requests.post(
                "http://localhost:8010/api/search/product-ids",
                json={
                    "index_name": "product_index",
                    "pipeline_id": "hybrid-minmax-pipeline",
                    "product_ids": product_ids,
                    "query": search_query,
                    "top_k": top_k
                }
            )
            response.raise_for_status()
            api_response = response.json()

            if isinstance(api_response, dict) and "results" in api_response:
                results = api_response["results"]
            else:
                results = api_response

            print(f"[INFO] 벡터 검색 결과: {len(results)}개")
            return results

        except Exception as e:
            print(f"[ERROR] 벡터 검색 실패: {e}")
            raise

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

        print(f"[INFO] 병합 완료: {len(merged)}개")
        return merged


@tool
def recommend_products(
    persona_id: str,
    purpose: Optional[str] = None,
    brands: Optional[List[str]] = None,
    product_categories: Optional[List[str]] = None,
    exclusive_target: Optional[str] = None
) -> str:
    """페르소나에 맞는 제품을 추천합니다.

    Args:
        persona_id: 페르소나 ID (필수)
        purpose: 메시지 목적 (예: "신상품홍보", "재구매유도")
        brands: 브랜드 필터 (예: ["설화수", "헤라"])
        product_categories: 상품 카테고리 필터 (예: ["립스틱", "크림"])
        exclusive_target: 특정 대상 전용 제품 (예: "임산부전용")

    Returns:
        추천 제품 리스트 (JSON 문자열):
        {
            "persona_info": {...},
            "search_query": "...",
            "products": [
                {
                    "product_id": "PROD001",
                    "상품명": "설화수 자음생크림",
                    "브랜드": "설화수",
                    "판매가": 150000,
                    "vector_search_score": 0.95,
                    ...
                }
            ]
        }
    """
    print(f"\n[recommend_products Tool 시작]")
    print(f"  - persona_id: {persona_id}")
    print(f"  - purpose: {purpose}")
    print(f"  - brands: {brands}")
    print(f"  - product_categories: {product_categories}")

    try:
        recommender = ProductRecommender()

        # 1. 페르소나 정보 조회
        persona_info = recommender.get_persona_info(persona_id)

        # 2. 필터링된 상품 목록 가져오기
        all_products = recommender.get_filtered_products(
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target
        )

        if not all_products:
            return json.dumps({
                "error": "필터 조건에 맞는 상품이 없습니다.",
                "products": []
            }, ensure_ascii=False)

        product_ids = [p["product_id"] for p in all_products]

        # 3. 검색 쿼리 생성
        search_query = recommender.create_search_query(
            persona_info=persona_info,
            purpose=purpose,
            brands=brands,
            product_categories=product_categories
        )

        # 4. 벡터 검색
        search_results = recommender.search_products(
            product_ids=product_ids,
            search_query=search_query,
            top_k=3
        )

        # 5. 데이터 병합
        merged_products = recommender.merge_product_data(
            search_results=search_results,
            all_products=all_products
        )

        # 6. 결과 반환 (JSON 문자열)
        result = {
            "persona_info": persona_info,
            "search_query": search_query,
            "products": merged_products,
            "count": len(merged_products)
        }

        print(f"[recommend_products Tool 완료] {len(merged_products)}개 상품 추천")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        error_result = {
            "error": str(e),
            "products": []
        }
        return json.dumps(error_result, ensure_ascii=False)
