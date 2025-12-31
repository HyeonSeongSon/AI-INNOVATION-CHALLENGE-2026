"""
ReAct Agent용 도구 정의
**추후 기능 추가 예정**
"""

from langchain_core.tools import tool
from typing import List, Dict, Any
import time


# Mock 데이터 저장소 (실제로는 DB/API)
MOCK_STORAGE = {}


@tool
def get_persona_info(persona_id: str) -> dict:
    """
    페르소나 ID로 API 키와 태그 정보를 조회합니다.

    Args:
        persona_id: 페르소나 고유 ID (예: "P123")

    Returns:
        페르소나 정보 (api_key, tags, persona_name 포함)

    중요: 이 도구를 가장 먼저 호출해야 합니다.
    """
    time.sleep(0.1)  # API 호출 시뮬레이션

    persona_info = {
        "api_key": "sk-mock-api-key-12345",
        "tags": ["20대", "여성", "민감성피부", "자연주의"],
        "persona_name": "민감성 피부 20대 여성"
    }

    # 저장 (나중에 사용)
    MOCK_STORAGE[f"persona_{persona_id}"] = persona_info

    return persona_info


@tool
def search_products(
    product_category: str,
    brand: str,
    exclusive_product: bool,
    persona_tags: List[str]
) -> dict:
    """
    카테고리, 브랜드, 태그로 상품을 검색합니다.

    Args:
        product_category: 상품 카테고리 (예: "스킨케어")
        brand: 브랜드명 (예: "라네즈")
        exclusive_product: 전용제품 여부 (True/False)
        persona_tags: 페르소나 태그 리스트 (예: ["20대", "여성"])

    Returns:
        검색된 상품 ID 리스트와 개수

    중요: get_persona_info를 먼저 호출하여 persona_tags를 얻어야 합니다.
    """
    time.sleep(0.15)  # API 호출 시뮬레이션

    # 상품 ID 생성
    product_ids = [
        f"PROD-{brand[:3].upper()}-{i:03d}"
        for i in range(1, 21)
    ]

    # 저장
    MOCK_STORAGE["product_ids"] = product_ids

    return {
        "product_ids": product_ids,
        "product_count": len(product_ids),
        "category": product_category,
        "brand": brand
    }


@tool
def search_vector_documents(
    purpose: str,
    product_category: str,
    persona_tags: List[str],
    product_ids: List[str],
    top_k: int = 5
) -> dict:
    """
    벡터 DB에서 관련 상품 문서를 검색합니다.

    Args:
        purpose: 메시지 목적 (예: "프로모션", "재구매유도")
        product_category: 상품 카테고리
        persona_tags: 페르소나 태그 리스트
        product_ids: 검색할 상품 ID 리스트
        top_k: 반환할 상위 문서 개수 (기본: 5)

    Returns:
        추천 상품 리스트 (product_id, product_name, relevance_score, description 포함)

    중요: search_products를 먼저 호출하여 product_ids를 얻어야 합니다.
    """
    time.sleep(0.2)  # 벡터 검색 시뮬레이션

    # Mock 추천 상품 생성
    brand = MOCK_STORAGE.get("brand", "Brand")

    recommended_products = [
        {
            "product_id": product_ids[i] if i < len(product_ids) else f"PROD-{i:03d}",
            "product_name": f"{brand} 제품 {i+1}",
            "relevance_score": 0.95 - (i * 0.05),
            "description": f"{product_category} 제품으로 {persona_tags[0] if persona_tags else '고객'}에게 추천",
            "price": 30000 + (i * 5000),
            "url": f"https://shop.example.com/products/{product_ids[i] if i < len(product_ids) else f'PROD-{i:03d}'}"
        }
        for i in range(min(top_k, len(product_ids)))
    ]

    # 저장
    MOCK_STORAGE["recommended_products"] = recommended_products

    return {
        "recommended_products": recommended_products,
        "total_count": len(recommended_products)
    }


@tool
def request_user_selection(recommended_products: List[dict]) -> dict:
    """
    추천 상품 목록을 사용자에게 보여주고 선택을 요청합니다.
    이 도구는 인터럽트를 발생시킵니다.

    Args:
        recommended_products: 추천 상품 리스트

    Returns:
        인터럽트 상태 메시지

    중요: search_vector_documents를 먼저 호출하여 recommended_products를 얻어야 합니다.
    이 도구 호출 후 에이전트는 멈추고 사용자의 선택을 기다립니다.
    """
    MOCK_STORAGE["recommended_products"] = recommended_products

    return {
        "status": "waiting_for_user_selection",
        "recommended_products": recommended_products,
        "message": "사용자가 상품을 선택할 때까지 대기 중입니다."
    }


@tool
def generate_final_message(
    purpose: str,
    brand: str,
    persona_name: str,
    selected_product_id: str,
    persona_tags: List[str]
) -> dict:
    """
    선택된 상품으로 최종 CRM 메시지를 생성합니다.

    Args:
        purpose: 메시지 목적 (예: "프로모션")
        brand: 브랜드명
        persona_name: 페르소나 이름
        selected_product_id: 선택된 상품 ID
        persona_tags: 페르소나 태그 리스트

    Returns:
        생성된 메시지, 상품 URL, 상품 정보

    중요: request_user_selection 이후, 사용자가 상품을 선택한 후에만 호출해야 합니다.
    """
    time.sleep(0.3)  # LLM 호출 시뮬레이션

    # 선택된 상품 찾기
    recommended_products = MOCK_STORAGE.get("recommended_products", [])
    selected_product = None

    for product in recommended_products:
        if product["product_id"] == selected_product_id:
            selected_product = product
            break

    if not selected_product:
        selected_product = recommended_products[0] if recommended_products else {
            "product_id": selected_product_id,
            "product_name": "선택된 제품",
            "description": "제품 설명",
            "price": 50000,
            "url": "https://shop.example.com"
        }

    # Mock LLM 메시지 생성
    final_message = f"""
안녕하세요! {persona_name}님을 위한 특별한 제안입니다.

{purpose} 이벤트로 {selected_product['product_name']}을(를) 소개합니다.

{selected_product['description']}

지금 바로 확인해보세요!
특별 가격: {selected_product['price']:,}원

[{brand}] 브랜드가 {', '.join(persona_tags[:2])}인 고객님을 위해 준비했습니다.
    """.strip()

    return {
        "message": final_message,
        "product_url": selected_product["url"],
        "product_info": {
            "product_id": selected_product["product_id"],
            "product_name": selected_product["product_name"],
            "price": selected_product["price"]
        }
    }


# 모든 도구를 리스트로 내보내기
ALL_TOOLS = [
    get_persona_info,
    search_products,
    search_vector_documents,
    request_user_selection,
    generate_final_message
]
