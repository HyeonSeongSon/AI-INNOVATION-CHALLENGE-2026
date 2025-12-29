import os
import json
import requests
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from dotenv import load_dotenv

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../../.env"))


class BasicRecommendProducts:
    def __init__(self,
                 persona_id: str,
                 purpose: Optional[str] = None,
                 brands: Optional[List[str]] = None,
                 product_categories: Optional[List[str]] = None,
                 exclusive_target: Optional[str] = None):
        """
        상품 추천 클래스

        Args:
            persona_id: 페르소나 ID (필수)
            purpose: 메시지 목적 (선택)
            brands: 브랜드 리스트 (선택)
            product_categories: 상품 카테고리 리스트 (선택)
            exclusive_target: 특정 대상 전용 제품 (선택)
        """
        self.persona_id = persona_id
        self.purpose = purpose
        self.brands = brands or []
        self.product_categories = product_categories or []
        self.exclusive_target = exclusive_target

        # LLM 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=api_key
        )

    def get_persona_info(self) -> Dict[str, Any]:
        """
        페르소나 ID로 PostgreSQL에서 페르소나 정보 가져오기

        Returns:
            페르소나 정보 딕셔너리
        """
        # TODO: 실제 DB 엔드포인트 호출
        # 예시: response = requests.post("http://api/personas/get", json={"persona_id": self.persona_id})
        # persona_info = response.json()

        # Mock 데이터 (실제 구현 시 제거)
        persona_info = {
            "persona_id": self.persona_id,
            "이름": "지민",
            "나이": 25,
            "성별": "여성",
            "피부타입": ["민감성", "복합성"],
            "고민 키워드": ["모공", "트러블", "피부 진정", "수분 부족"],
            "퍼스널 컬러": ["쿨톤"],
            "베이스 호수": 21,
            "메이크업 선호 색상": ["핑크", "코랄", "라벤더"],
            "선호 성분": ["센텔라", "나이아신아마이드", "히알루론산", "세라마이드"],
            "기피 성분": ["알코올", "인공향료", "파라벤", "미네랄 오일"],
            "선호 향": "무향 또는 은은한 플로럴",
            "가치관": ["동물실험 반대", "비건 화장품 선호", "친환경 포장"],
            "스킨케어 루틴": "10단계 (이중 세안, 토너, 에센스, 세럼, 크림, 선크림 등)",
            "주 활동 환경": ["사무실 (에어컨)", "대중교통", "카페"],
            "선호 제형(텍스처)": ["크림", "젤", "로션"],
            "반려동물": "고양이",
            "수면 시간": "6시간",
            "스트레스": "높음",
            "거주지역": "서울 강남구",
            "디지털 기기 사용": "하루 10시간 이상",
            "쇼핑 스타일&예산": "온라인 쇼핑 선호, 월 15만원",
            "구매 결정 요인": ["리뷰", "성분", "브랜드 신뢰도", "가격"]
        }

        return persona_info

    def get_product_info(self) -> List[Dict[str, Any]]:
        """
        페르소나 정보와 필터 조건에 맞는 상품을 PostgreSQL에서 가져오기

        Returns:
            상품 정보 리스트
        """
        # 필터 조건 생성
        filters = {
            "persona_id": self.persona_id,
        }

        # 값이 있는 것만 필터에 추가
        if self.brands:
            filters["brands"] = self.brands
        if self.product_categories:
            filters["product_categories"] = self.product_categories
        if self.exclusive_target:
            filters["exclusive_target"] = self.exclusive_target

        # TODO: 실제 DB 엔드포인트 호출
        # 예시: response = requests.post("http://api/products/filter", json=filters)
        # product_info = response.json()

        # Mock 데이터: espoir_products_filtered.jsonl에서 읽기 (실제 구현 시 제거)
        jsonl_path = os.path.join(os.path.dirname(__file__), "espoir_products_filtered.jsonl")

        product_info = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    product = json.loads(line.strip())
                    product_info.append(product)

            print(f"[INFO] JSONL에서 {len(product_info)}개 상품 로드 완료")

        except FileNotFoundError:
            print(f"[WARNING] {jsonl_path} 파일을 찾을 수 없습니다. 빈 리스트 반환.")
        except Exception as e:
            print(f"[ERROR] JSONL 파일 읽기 실패: {e}")

        return product_info

    def create_persona_analysis_content(self, persona_info: Dict[str, Any]) -> str:
        """
        페르소나 정보와 캠페인 정보를 사용하여 벡터 검색용 쿼리 생성

        Args:
            persona_info: 페르소나 정보 딕셔너리

        Returns:
            생성된 검색 쿼리 문자열
        """
        # 페르소나 정보 포맷팅 (값이 있는 것만 포함)
        persona_sections = []

        # 기본 정보
        if persona_info.get('이름'):
            persona_sections.append(f"- 이름: {persona_info['이름']}")
        if persona_info.get('나이'):
            persona_sections.append(f"- 나이: {persona_info['나이']}세")
        if persona_info.get('성별'):
            persona_sections.append(f"- 성별: {persona_info['성별']}")
        if persona_info.get('거주지역'):
            persona_sections.append(f"- 거주지역: {persona_info['거주지역']}")

        # 피부 정보
        if persona_info.get('피부타입'):
            persona_sections.append(f"- 피부타입: {persona_info['피부타입']}")
        if persona_info.get('고민 키워드'):
            persona_sections.append(f"- 피부 고민: {', '.join(persona_info['고민 키워드'])}")

        # 뷰티 정보
        if persona_info.get('퍼스널 컬러'):
            persona_sections.append(f"- 퍼스널 컬러: {persona_info['퍼스널 컬러']}")
        if persona_info.get('베이스 호수'):
            persona_sections.append(f"- 베이스 호수: {persona_info['베이스 호수']}")
        if persona_info.get('메이크업 선호 색상'):
            persona_sections.append(f"- 선호 색상: {', '.join(persona_info['메이크업 선호 색상'])}")

        # 성분 선호도
        if persona_info.get('선호 성분'):
            persona_sections.append(f"- 선호 성분: {', '.join(persona_info['선호 성분'])}")
        # if persona_info.get('기피 성분'):
        #     persona_sections.append(f"- 기피 성분: {', '.join(persona_info['기피 성분'])}")
        if persona_info.get('선호 향'):
            persona_sections.append(f"- 선호 향: {persona_info['선호 향']}")

        # 제형 및 루틴
        if persona_info.get('선호 제형(텍스처)'):
            persona_sections.append(f"- 선호 제형: {', '.join(persona_info['선호 제형(텍스처)'])}")
        if persona_info.get('스킨케어 루틴'):
            persona_sections.append(f"- 스킨케어 루틴: {persona_info['스킨케어 루틴']}")

        # 라이프스타일
        if persona_info.get('주 활동 환경'):
            persona_sections.append(f"- 주 활동 환경: {', '.join(persona_info['주 활동 환경'])}")
        if persona_info.get('수면 시간'):
            persona_sections.append(f"- 수면 시간: {persona_info['수면 시간']}")
        if persona_info.get('스트레스'):
            persona_sections.append(f"- 스트레스 수준: {persona_info['스트레스']}")
        if persona_info.get('디지털 기기 사용'):
            persona_sections.append(f"- 디지털 기기 사용: {persona_info['디지털 기기 사용']}")

        # 특수 정보
        if persona_info.get('반려동물'):
            persona_sections.append(f"- 반려동물: {persona_info['반려동물']}")
        if persona_info.get('가치관'):
            persona_sections.append(f"- 가치관: {', '.join(persona_info['가치관'])}")

        # 구매 정보
        if persona_info.get('쇼핑 스타일&예산'):
            persona_sections.append(f"- 쇼핑 스타일: {persona_info['쇼핑 스타일&예산']}")
        if persona_info.get('구매 결정 요인'):
            persona_sections.append(f"- 구매 결정 요인: {', '.join(persona_info['구매 결정 요인'])}")

        persona_text = "## 페르소나 정보\n" + "\n".join(persona_sections)

        # 캠페인 정보를 동적으로 생성 (값이 있는 것만 포함)
        campaign_sections = []

        if self.purpose:
            campaign_sections.append(f"- 목적: {self.purpose}")

        if self.brands:
            campaign_sections.append(f"- 브랜드: {', '.join(self.brands)}")

        if self.product_categories:
            campaign_sections.append(f"- 타겟 제품군: {', '.join(self.product_categories)}")

        if self.exclusive_target:
            campaign_sections.append(f"- 전용 제품: {self.exclusive_target}")

        # 캠페인 정보가 있으면 섹션 추가
        campaign_info = ""
        if campaign_sections:
            campaign_info = "\n## 캠페인 정보\n" + "\n".join(campaign_sections)

        # 전체 프롬프트 생성
        prompt = f"""
{campaign_info}
{persona_text}

위 캠페인 정보(목적, 브랜드, 타겟 제품군)를 바탕으로 페르소나의 특성을 참고하여 제품 검색 쿼리를 한 문장으로 작성하세요.

**작성 규칙**:
1. 캠페인의 목적, 브랜드, 타겟 제품군을 반드시 포함하세요.
2. 페르소나의 피부 타입, 고민, 선호 성분, 가치관 중 캠페인과 관련된 내용을 선택적으로 포함하세요.
3. 반드시 한 문장으로만 작성하세요.
4. 추가 설명, 제목, 부연 설명 없이 검색 쿼리 문장만 출력하세요.
"""

        print(f'<<<검색 쿼리 프롬프트>>>\n{prompt}')
        # LLM으로 검색 쿼리 생성
        try:
            response = self.llm.invoke(prompt)
            search_query = response.content
            print(f"[INFO] 생성된 검색 쿼리:\n{search_query}\n")
            return search_query
        except Exception as e:
            print(f"[ERROR] LLM 호출 실패: {e}")
            # 폴백: 기본 검색 쿼리 생성
            fallback_query = f"{persona_info.get('persona_name', '')} 피부에 맞는 "
            if self.product_categories:
                fallback_query += f"{', '.join(self.product_categories)} "
            if self.brands:
                fallback_query += f"{', '.join(self.brands)} "
            fallback_query += "제품"
            return fallback_query

    def recommend_products(self) -> Dict[str, Any]:
        """
        전체 추천 프로세스 실행

        1. 페르소나 정보 가져오기
        2. 상품 정보 가져오기
        3. 검색 쿼리 생성
        4. 벡터 DB에서 유사 상품 검색

        Returns:
            추천 결과 딕셔너리
        """
        # 1. 페르소나 정보 가져오기
        print(f"[INFO] 페르소나 정보 조회: {self.persona_id}")
        persona_info = self.get_persona_info()

        # 2. 상품 정보 가져오기 (필터링된 상품)
        print(f"[INFO] 상품 정보 조회")
        product_info = self.get_product_info()

        # 상품 ID 리스트 추출
        product_ids = [p["product_id"] for p in product_info]
        print(f"[INFO] 필터링된 상품 개수: {len(product_ids)}")

        # 3. 검색 쿼리 생성
        print(f"[INFO] 검색 쿼리 생성 중...")
        search_query = self.create_persona_analysis_content(persona_info)

        # 4. 벡터 DB에서 유사 상품 검색
        print(f"[INFO] 벡터 DB 검색 중...")

        # TODO: 실제 벡터 DB 엔드포인트 호출
        response = requests.post(
            "http://localhost:8010/api/search/product-ids",
            json={
                "index_name": "product_index",
                "pipeline_id": "hybrid-minmax-pipeline",
                "product_ids": product_ids,
                "query": search_query,
                "top_k": 3
            }
        )
        api_response = response.json()

        # API 응답에서 results 필드 추출
        if isinstance(api_response, dict) and "results" in api_response:
            recommended_products = api_response["results"]
        else:
            # 응답이 이미 리스트 형태인 경우
            recommended_products = api_response

        return {
            "success": True,
            "persona_info": persona_info,
            "search_query": search_query,
            "recommended_products": recommended_products,
            "count": len(recommended_products),
            "filters": {
                "purpose": self.purpose,
                "brands": self.brands,
                "product_categories": self.product_categories,
                "exclusive_target": self.exclusive_target
            }
        }


# ============================================================
# LangChain Tool 래퍼
# ============================================================

# 싱글톤 패턴으로 인스턴스 재사용 (선택적)
_recommender_cache = {}

def _get_recommender(persona_id: str,
                     purpose: Optional[str],
                     brands: Optional[List[str]],
                     product_categories: Optional[List[str]],
                     exclusive_target: Optional[str]) -> BasicRecommendProducts:
    """
    추천 시스템 인스턴스 가져오기 (캐싱)
    """
    cache_key = f"{persona_id}_{purpose}_{brands}_{product_categories}_{exclusive_target}"

    if cache_key not in _recommender_cache:
        _recommender_cache[cache_key] = BasicRecommendProducts(
            persona_id=persona_id,
            purpose=purpose,
            brands=brands,
            product_categories=product_categories,
            exclusive_target=exclusive_target
        )

    return _recommender_cache[cache_key]


@tool
def recommend_products_tool(
    persona_id: str,
    purpose: Optional[str] = None,
    brands: Optional[List[str]] = None,
    product_categories: Optional[List[str]] = None,
    exclusive_target: Optional[str] = None
) -> Dict[str, Any]:
    """
    페르소나와 캠페인 정보를 기반으로 상품을 추천합니다.

    Args:
        persona_id: 페르소나 ID (필수)
        purpose: 메시지 목적 (예: '프로모션', '재구매유도')
        brands: 브랜드 리스트 (예: ['라네즈', '설화수'])
        product_categories: 상품 카테고리 리스트 (예: ['스킨케어', '메이크업'])
        exclusive_target: 특정 대상 전용 제품 (예: '남성', '반려동물', '베이비')

    Returns:
        추천 결과 딕셔너리
        - persona_info: 페르소나 정보
        - search_query: 생성된 검색 쿼리
        - recommended_products: 추천 상품 리스트
        - count: 추천 상품 개수
    """
    recommender = BasicRecommendProducts(
        persona_id=persona_id,
        purpose=purpose,
        brands=brands,
        product_categories=product_categories,
        exclusive_target=exclusive_target
    )

    result = recommender.recommend_products()
    return result


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== BasicRecommendProducts 테스트 ===\n")

    # 테스트 1
    print("[테스트 1] 모든 매개변수 사용")
    print("=" * 80)

    result1 = recommend_products_tool.invoke({
        "persona_id": "P123",
        "purpose": "프로모션",
        "brands": ["에스쁘아"],
        "product_categories": ["립스틱"],
        "exclusive_target": None
    })

    print(f"\n추천 결과:")
    print(f"- 페르소나: {result1['persona_info'].get('이름', 'N/A')} ({result1['persona_info'].get('나이', 'N/A')}세, {result1['persona_info'].get('성별', 'N/A')})")
    print(f"- 피부타입: {result1['persona_info'].get('피부타입', 'N/A')}")
    print(f"- 추천 상품 수: {result1['count']}")
    print(f"- 검색 쿼리:\n{result1['search_query']}")
    print(f"\n추천 상품 원본:")
    print(result1['recommended_products'])
    print(f"\n추천 상품:")
    if isinstance(result1['recommended_products'], list) and len(result1['recommended_products']) > 0:
        for product in result1['recommended_products']:
            if isinstance(product, dict):
                print(f"  - {product.get('product_name', product.get('상품명', 'N/A'))} (점수: {product.get('relevance_score', product.get('score', 'N/A'))})")
            else:
                print(f"  - {product}")
    else:
        print(f"  추천 상품 형식: {type(result1['recommended_products'])}")