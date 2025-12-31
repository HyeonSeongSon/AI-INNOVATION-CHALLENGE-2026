"""
스마트 상품 검색 Tool
상품이 부족하면 자동으로 필터를 완화하여 재검색
"""

from langchain_core.tools import tool
from typing import List, Dict, Any, Optional
import time


@tool
def smart_product_search(
    product_category: str,
    brand: Optional[str] = None,
    exclusive_product: Optional[bool] = None,
    persona_tags: Optional[List[str]] = None,
    min_products: int = 5
) -> dict:
    """
    상품을 검색하고, 결과가 부족하면 자동으로 필터를 완화하여 재검색합니다.

    Args:
        product_category: 상품 카테고리 (예: "스킨케어")
        brand: 브랜드명 (예: "라네즈")
        exclusive_product: 전용제품 여부
        persona_tags: 페르소나 태그 리스트
        min_products: 최소 필요 상품 개수 (기본: 5)

    Returns:
        검색 결과와 재시도 정보
    """

    search_attempts = []

    # None 처리
    if persona_tags is None:
        persona_tags = []

    # ========================================
    # 1차 시도: 모든 필터 적용
    # ========================================
    print(f"[1차 검색] 모든 필터 적용 (브랜드: {brand}, 전용제품: {exclusive_product})")

    products = _search_products(
        category=product_category,
        brand=brand,
        exclusive=exclusive_product,
        tags=persona_tags
    )

    search_attempts.append({
        "attempt": 1,
        "filters": f"브랜드={brand}, 전용제품={exclusive_product}",
        "count": len(products)
    })

    print(f"   결과: {len(products)}개 발견")

    # 충분하면 바로 리턴
    if len(products) >= min_products:
        return {
            "success": True,
            "products": products[:20],  # 최대 20개
            "count": len(products),
            "attempts": search_attempts,
            "filter_relaxed": False,
            "message": f"충분한 상품 발견 ({len(products)}개)"
        }

    # ========================================
    # 2차 시도: 전용제품 필터 제거
    # ========================================
    print(f"[2차 검색] 전용제품 필터 제거 (상품 부족: {len(products)}개 < {min_products}개)")

    products = _search_products(
        category=product_category,
        brand=brand,
        exclusive=None,  # 전용제품 필터 제거
        tags=persona_tags
    )

    search_attempts.append({
        "attempt": 2,
        "filters": f"브랜드={brand}, 전용제품=모두",
        "count": len(products)
    })

    print(f"   결과: {len(products)}개 발견")

    # 충분하면 리턴
    if len(products) >= min_products:
        return {
            "success": True,
            "products": products[:20],
            "count": len(products),
            "attempts": search_attempts,
            "filter_relaxed": True,
            "message": f"전용제품 필터 제거 후 {len(products)}개 발견"
        }

    # ========================================
    # 3차 시도: 브랜드 필터도 제거
    # ========================================
    print(f"[3차 검색] 브랜드 필터도 제거 (여전히 부족: {len(products)}개 < {min_products}개)")

    products = _search_products(
        category=product_category,
        brand=None,  # 브랜드 필터 제거
        exclusive=None,
        tags=persona_tags
    )

    search_attempts.append({
        "attempt": 3,
        "filters": f"브랜드=모두, 전용제품=모두",
        "count": len(products)
    })

    print(f"   결과: {len(products)}개 발견")

    # 충분하면 리턴
    if len(products) >= min_products:
        return {
            "success": True,
            "products": products[:20],
            "count": len(products),
            "attempts": search_attempts,
            "filter_relaxed": True,
            "message": f"브랜드 필터 제거 후 {len(products)}개 발견"
        }

    # ========================================
    # 4차 시도: 페르소나 태그도 완화 (일부만 적용)
    # ========================================
    print(f"[4차 검색] 페르소나 태그 완화 (여전히 부족: {len(products)}개 < {min_products}개)")

    # 태그를 2개만 사용 (가장 중요한 것)
    relaxed_tags = persona_tags[:2] if len(persona_tags) > 2 else persona_tags

    products = _search_products(
        category=product_category,
        brand=None,
        exclusive=None,
        tags=relaxed_tags
    )

    search_attempts.append({
        "attempt": 4,
        "filters": f"태그={relaxed_tags} (완화됨)",
        "count": len(products)
    })

    print(f"   결과: {len(products)}개 발견")

    # 여전히 부족해도 리턴
    if len(products) < min_products:
        return {
            "success": False,
            "products": products,
            "count": len(products),
            "attempts": search_attempts,
            "filter_relaxed": True,
            "message": f"최대한 완화했지만 {len(products)}개만 발견 (목표: {min_products}개)"
        }

    return {
        "success": True,
        "products": products[:20],
        "count": len(products),
        "attempts": search_attempts,
        "filter_relaxed": True,
        "message": f"페르소나 태그 완화 후 {len(products)}개 발견"
    }


def _search_products(
    category: str,
    brand: str = None,
    exclusive: bool = None,
    tags: List[str] = None
) -> List[Dict[str, Any]]:
    """
    실제 상품 검색 (Mock)
    실제로는 DB 쿼리 또는 API 호출
    """
    time.sleep(0.1)  # API 호출 시뮬레이션

    # Mock 데이터 생성
    # 브랜드가 있으면 적게, 없으면 많이
    if brand:
        if exclusive:
            count = 2  # 브랜드 + 전용제품 → 매우 적음
        else:
            count = 8  # 브랜드만 → 적음
    else:
        if exclusive:
            count = 12  # 전용제품만 → 중간
        else:
            count = 25  # 필터 없음 → 많음

    # 태그로 추가 필터링
    if tags and len(tags) > 2:
        count = max(2, count - 3)  # 태그 많으면 더 적어짐

    products = []
    for i in range(count):
        products.append({
            "product_id": f"PROD-{category[:3].upper()}-{i:03d}",
            "product_name": f"{brand or '일반'} {category} {i+1}",
            "category": category,
            "brand": brand or "다양한 브랜드",
            "exclusive": exclusive if exclusive is not None else (i % 2 == 0),
            "price": 30000 + (i * 5000),
            "tags": tags[:2] if tags else []
        })

    return products


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== 스마트 상품 검색 테스트 ===\n")

    # 테스트 1: 상품 부족한 케이스
    print("\n[테스트 1] 상품 부족 - 필터 완화 필요")
    print("-" * 70)

    result = smart_product_search.invoke({
        "product_category": "스킨케어",
        "brand": "희귀브랜드",  # 희귀한 브랜드 → 상품 적음
        "exclusive_product": True,  # 전용제품 → 더 적음
        "persona_tags": ["20대", "여성", "민감성피부", "자연주의"],
        "min_products": 5
    })

    print(f"\n최종 결과:")
    print(f"  성공: {result['success']}")
    print(f"  상품 개수: {result['count']}")
    print(f"  필터 완화: {result['filter_relaxed']}")
    print(f"  메시지: {result['message']}")

    print(f"\n시도 기록:")
    for attempt in result['attempts']:
        print(f"  [{attempt['attempt']}차] {attempt['filters']} → {attempt['count']}개")

    print(f"\n상품 샘플 (상위 3개):")
    for i, product in enumerate(result['products'][:3], 1):
        print(f"  {i}. {product['product_name']} - {product['brand']}")

    # 테스트 2: 상품 충분한 케이스
    print("\n" + "=" * 70)
    print("\n[테스트 2] 상품 충분 - 필터 완화 불필요")
    print("-" * 70)

    result = smart_product_search.invoke({
        "product_category": "스킨케어",
        "brand": None,  # 브랜드 제한 없음
        "exclusive_product": False,
        "persona_tags": ["20대"],
        "min_products": 5
    })

    print(f"\n최종 결과:")
    print(f"  성공: {result['success']}")
    print(f"  상품 개수: {result['count']}")
    print(f"  필터 완화: {result['filter_relaxed']}")
    print(f"  메시지: {result['message']}")

    print(f"\n시도 기록:")
    for attempt in result['attempts']:
        print(f"  [{attempt['attempt']}차] {attempt['filters']} → {attempt['count']}개")
