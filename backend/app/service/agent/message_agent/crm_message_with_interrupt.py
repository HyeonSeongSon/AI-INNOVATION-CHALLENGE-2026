"""
상품 추천 워크플로우 (LangGraph StateGraph)
사용자 인터럽트를 지원하는 상품 추천 프로세스
Tool로 래핑되어 crm_message_hierarchical.py에서 사용됨
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator
import os
import json
import uuid
import requests
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


# ============================================================
# State 정의
# ============================================================

class ProductRecommendationState(TypedDict):
    """
    상품 추천 워크플로우 State
    """
    # 입력
    persona_id: str
    purpose: Optional[str]
    brands: Optional[List[str]]
    product_categories: Optional[List[str]]
    exclusive_target: Optional[str]

    # 추천 결과
    persona_info: Optional[Dict[str, Any]]
    search_query: Optional[str]
    recommended_products: Optional[List[Dict[str, Any]]]  # 벡터 검색 결과
    merged_products: Optional[List[Dict[str, Any]]]  # 병합된 결과

    # 사용자 선택
    selected_product_index: Optional[int]
    selected_product: Optional[Dict[str, Any]]


# ============================================================
# BasicRecommendProducts 클래스
# ============================================================

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
        JSONL 파일에서 상품 정보 가져오기

        Returns:
            상품 정보 리스트
        """
        # TODO: 필터 조건 생성
        # filters = {
        #     "persona_id": self.persona_id,
        # }

        # 값이 있는 것만 필터에 추가
        # if self.brands:
        #     filters["brands"] = self.brands
        # if self.product_categories:
        #     filters["product_categories"] = self.product_categories
        # if self.exclusive_target:
        #     filters["exclusive_target"] = self.exclusive_target

        # TODO: 실제 DB 엔드포인트 호출
        # 예시: response = requests.post("http://api/products/filter", json=filters)
        # product_info = response.json()

        jsonl_path = os.path.join(os.path.dirname(__file__), "tools/espoir_products_filtered.jsonl")

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
        """
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

        # 캠페인 정보
        campaign_sections = []
        if self.purpose:
            campaign_sections.append(f"- 목적: {self.purpose}")
        if self.brands:
            campaign_sections.append(f"- 브랜드: {', '.join(self.brands)}")
        if self.product_categories:
            campaign_sections.append(f"- 타겟 제품군: {', '.join(self.product_categories)}")
        if self.exclusive_target:
            campaign_sections.append(f"- 전용 제품: {self.exclusive_target}")

        campaign_info = ""
        if campaign_sections:
            campaign_info = "\n## 캠페인 정보\n" + "\n".join(campaign_sections)

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
        try:
            response = self.llm.invoke(prompt)
            search_query = response.content
            print(f"[INFO] 생성된 검색 쿼리:\n{search_query}\n")
            return search_query
        except Exception as e:
            print(f"[ERROR] LLM 호출 실패: {e}")
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
        """
        print(f"[INFO] 페르소나 정보 조회: {self.persona_id}")
        persona_info = self.get_persona_info()

        print(f"[INFO] 상품 정보 조회")
        product_info = self.get_product_info()

        product_ids = [p["product_id"] for p in product_info]
        print(f"[INFO] 필터링된 상품 개수: {len(product_ids)}")

        print(f"[INFO] 검색 쿼리 생성 중...")
        search_query = self.create_persona_analysis_content(persona_info)

        print(f"[INFO] 벡터 DB 검색 중...")
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

        if isinstance(api_response, dict) and "results" in api_response:
            recommended_products = api_response["results"]
        else:
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
# Node 함수들
# ============================================================

def recommend_products_node(state: ProductRecommendationState) -> Dict[str, Any]:
    """
    상품 추천 노드 (벡터 검색 실행)
    """
    print("\n[Node 1] 상품 추천 중...")

    # BasicRecommendProducts 인스턴스 생성 및 직접 호출
    recommender = BasicRecommendProducts(
        persona_id=state["persona_id"],
        purpose=state.get("purpose"),
        brands=state.get("brands"),
        product_categories=state.get("product_categories"),
        exclusive_target=state.get("exclusive_target")
    )

    result = recommender.recommend_products()

    return {
        "persona_info": result["persona_info"],
        "search_query": result["search_query"],
        "recommended_products": result["recommended_products"]  # 벡터 검색 결과 (score 포함)
    }


def merge_product_data_node(state: ProductRecommendationState) -> Dict[str, Any]:
    """
    벡터 검색 결과와 JSONL 원본 데이터를 병합하는 노드

    recommended_products: 벡터 검색 결과 (product_id, score 포함)
    JSONL 원본 데이터와 product_id 기준으로 매칭하여 병합
    """
    print("\n[Node 2] 상품 데이터 병합 중...")

    recommended = state["recommended_products"]

    # BasicRecommendProducts 인스턴스 생성 및 직접 호출
    recommender = BasicRecommendProducts(
        persona_id=state["persona_id"],
        purpose=state.get("purpose"),
        brands=state.get("brands"),
        product_categories=state.get("product_categories"),
        exclusive_target=state.get("exclusive_target")
    )

    # JSONL에서 전체 상품 데이터 로드
    all_products = recommender.get_product_info()

    # product_id를 키로 하는 딕셔너리 생성
    product_data_map = {p["product_id"]: p for p in all_products}

    # 벡터 검색 결과와 원본 데이터 병합
    merged_products = []
    for rec_product in recommended:
        product_id = rec_product.get("product_id")

        if product_id in product_data_map:
            # 원본 데이터 가져오기
            original_data = product_data_map[product_id].copy()

            # 벡터 검색 점수 추가
            original_data["vector_search_score"] = rec_product.get("score")

            # 벡터 검색 결과의 다른 필드도 추가 (있는 경우)
            for key in ["상품명", "브랜드", "태그"]:
                if key in rec_product and key not in original_data:
                    original_data[key] = rec_product[key]

            merged_products.append(original_data)
        else:
            # 매칭되는 데이터가 없으면 벡터 검색 결과만 사용
            merged_products.append(rec_product)

    print(f"[INFO] {len(merged_products)}개 상품 데이터 병합 완료")

    return {
        "merged_products": merged_products
    }


def wait_for_user_selection_node(state: ProductRecommendationState) -> Dict[str, Any]:
    """
    사용자 선택 대기 노드

    이 노드는 interrupt_before에 의해 실행 전에 멈춥니다.
    사용자가 선택한 후 update_state()로 selected_product_index를 설정하고 재개합니다.
    """
    print("\n[Node 3] 사용자 선택 대기 중...")

    # selected_product_index가 설정되어 있으면 선택된 상품 가져오기
    if state.get("selected_product_index") is not None:
        selected_idx = state["selected_product_index"]
        merged_products = state["merged_products"]

        if 0 <= selected_idx < len(merged_products):
            selected = merged_products[selected_idx]

            return {
                "selected_product": selected
            }
        else:
            print(f"[ERROR] 잘못된 선택 인덱스: {selected_idx}")
            return {}

    # 선택되지 않은 경우 (interrupt 시점)
    return {}


# ============================================================
# Workflow 구성
# ============================================================

def create_product_recommendation_workflow():
    """상품 추천 워크플로우 생성 (사용자 인터럽트 지원)"""

    # StateGraph 생성
    workflow = StateGraph(ProductRecommendationState)

    # 노드 추가
    workflow.add_node("recommend_products", recommend_products_node)
    workflow.add_node("merge_product_data", merge_product_data_node)
    workflow.add_node("wait_for_user_selection", wait_for_user_selection_node)

    # 엣지 연결
    workflow.set_entry_point("recommend_products")
    workflow.add_edge("recommend_products", "merge_product_data")
    workflow.add_edge("merge_product_data", "wait_for_user_selection")
    workflow.add_edge("wait_for_user_selection", END)

    # 체크포인터 설정
    checkpointer = MemorySaver()

    # 컴파일 (interrupt_before 설정)
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["wait_for_user_selection"]  # 사용자 선택 노드 전에 멈춤
    )

    return app


# 워크플로우 싱글톤 인스턴스
_workflow_app = None

def get_workflow_app():
    """워크플로우 앱 가져오기 (싱글톤)"""
    global _workflow_app
    if _workflow_app is None:
        _workflow_app = create_product_recommendation_workflow()
    return _workflow_app


# ============================================================
# Tool 래핑
# ============================================================

# 세션 관리용 전역 딕셔너리
_workflow_sessions = {}

@tool
def recommend_products(
    persona_id: Optional[str] = None,
    purpose: Optional[str] = None,
    brands: Optional[List[str]] = None,
    product_categories: Optional[List[str]] = None,
    exclusive_target: Optional[str] = None,
    thread_id: Optional[str] = None,
    selected_index: Optional[int] = None
) -> Dict[str, Any]:
    """
    상품 추천 워크플로우 (사용자 인터럽트 지원)

    **사용 방법:**

    [1차 호출 - 시작] persona_id와 캠페인 정보 제공
    → status="interrupted", thread_id, merged_products 반환

    [2차 호출 - 재개] thread_id와 selected_index 제공
    → status="completed", selected_product 반환

    Args:
        # 시작 시 필수
        persona_id: 페르소나 ID

        # 시작 시 선택
        purpose: 메시지 목적
        brands: 브랜드 리스트
        product_categories: 상품 카테고리 리스트
        exclusive_target: 전용 제품 대상

        # 재개 시 필수
        thread_id: 세션 ID (1차 호출에서 받은 값)
        selected_index: 사용자가 선택한 상품 인덱스 (0부터 시작)

    Returns:
        시작 시: {
            "status": "interrupted",
            "thread_id": "...",
            "merged_products": [...],
            "persona_info": {...},
            "search_query": "..."
        }

        재개 시: {
            "status": "completed",
            "selected_product": {...}
        }

        에러 시: {
            "status": "error",
            "error": "에러 메시지"
        }
    """
    app = get_workflow_app()

    # 1차 호출: 새로운 워크플로우 시작
    if persona_id is not None and thread_id is None:
        new_thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": new_thread_id}}

        initial_state = {
            "persona_id": persona_id,
            "purpose": purpose,
            "brands": brands,
            "product_categories": product_categories,
            "exclusive_target": exclusive_target
        }

        # interrupt_before까지 실행
        result = app.invoke(initial_state, config)

        # 세션 저장
        _workflow_sessions[new_thread_id] = config

        return {
            "status": "interrupted",
            "thread_id": new_thread_id,
            "merged_products": result.get("merged_products", []),
            "persona_info": result.get("persona_info", {}),
            "search_query": result.get("search_query", "")
        }

    # 2차 호출: 기존 워크플로우 재개
    elif thread_id is not None and selected_index is not None:
        if thread_id not in _workflow_sessions:
            return {
                "status": "error",
                "error": f"세션을 찾을 수 없습니다: {thread_id}"
            }

        config = _workflow_sessions[thread_id]

        # 사용자 선택 업데이트
        app.update_state(
            config,
            {"selected_product_index": selected_index}
        )

        # 나머지 노드 실행
        result = app.invoke(None, config)

        # 세션 정리
        del _workflow_sessions[thread_id]

        return {
            "status": "completed",
            "selected_product": result.get("selected_product", {})
        }

    # 파라미터 오류
    else:
        return {
            "status": "error",
            "error": "persona_id (시작) 또는 (thread_id + selected_index) (재개)를 제공해야 합니다"
        }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== 상품 추천 워크플로우 with User Interrupt 테스트 ===\n")

    # 1단계: 상품 추천 시작
    print("[1단계] 상품 추천 시작")
    print("=" * 80)

    result1 = recommend_products.invoke({
        "persona_id": "P123",
        "purpose": "프로모션",
        "brands": ["에스쁘아"],
        "product_categories": ["립스틱"],
        "exclusive_target": None
    })

    print(f"\n[상태] {result1.get('status')}")

    if result1.get("status") == "interrupted":
        print(f"[Thread ID] {result1.get('thread_id')}")

        print(f"\n[페르소나 정보]")
        persona = result1["persona_info"]
        print(f"  - 이름: {persona.get('이름', 'N/A')}")
        print(f"  - 나이/성별: {persona.get('나이', 'N/A')}세 / {persona.get('성별', 'N/A')}")
        print(f"  - 피부타입: {persona.get('피부타입', 'N/A')}")

        print(f"\n[검색 쿼리]")
        print(f"  {result1['search_query']}")

        print(f"\n[추천 상품 목록] (총 {len(result1['merged_products'])}개)")
        print("=" * 80)

        merged_products = result1["merged_products"]
        for idx, product in enumerate(merged_products):
            print(f"\n{idx + 1}. {product.get('상품명', 'N/A')}")
            print(f"   - 브랜드: {product.get('브랜드', 'N/A')}")
            print(f"   - 태그: {product.get('태그', 'N/A')}")
            print(f"   - 가격: {product.get('판매가', 'N/A'):,}원 (할인율: {product.get('할인율', 0)}%)")
            print(f"   - 별점: {product.get('별점', 'N/A')} ({product.get('리뷰_갯수', 0)}개 리뷰)")
            print(f"   - 벡터 검색 점수: {product.get('vector_search_score', 'N/A')}")

        # 사용자 선택 입력
        print("\n" + "=" * 80)
        while True:
            try:
                user_input = input(f"선택할 상품 번호를 입력하세요 (1-{len(merged_products)}): ")
                selected_index = int(user_input) - 1

                if 0 <= selected_index < len(merged_products):
                    print(f"[사용자 선택] {selected_index + 1}번 상품 선택")
                    break
                else:
                    print(f"잘못된 번호입니다. 1부터 {len(merged_products)} 사이의 숫자를 입력하세요.")
            except ValueError:
                print("숫자를 입력해주세요.")
            except KeyboardInterrupt:
                print("\n프로그램을 종료합니다.")
                exit(0)

        # 2단계: 선택 완료 (재개)
        print("\n[2단계] 사용자 선택 완료")
        print("=" * 80)

        result2 = recommend_products.invoke({
            "thread_id": result1["thread_id"],
            "selected_index": selected_index
        })

        print(f"\n[상태] {result2.get('status')}")

        if result2.get("status") == "completed":
            print(f"\n[선택된 상품]")
            selected_product = result2["selected_product"]
            print(f"  상품명: {selected_product.get('상품명', 'N/A')}")
            print(f"  브랜드: {selected_product.get('브랜드', 'N/A')}")
            print(f"  가격: {selected_product.get('판매가', 'N/A'):,}원")
            print(f"  벡터 검색 점수: {selected_product.get('vector_search_score', 'N/A')}")
        elif result2.get("status") == "error":
            print(f"\n[에러] {result2.get('error')}")
    elif result1.get("status") == "error":
        print(f"\n[에러] {result1.get('error')}")
