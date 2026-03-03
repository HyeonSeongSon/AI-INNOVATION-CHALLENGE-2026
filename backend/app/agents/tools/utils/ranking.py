"""
상품 순위 계산 유틸리티
"""

from typing import Any


def rank_and_top5(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    별점(rating)과 리뷰수(review_count) 각각의 순위를 구하고,
    두 순위의 평균이 낮은(= 상위) 순으로 상위 5개 상품을 반환합니다.

    Args:
        products: DB API 응답 dict 리스트

    Returns:
        평균 순위 기준 상위 5개 dict 리스트
    """
    if not products:
        return []

    n = len(products)

    def safe_float(v):
        return float(v) if v is not None else 0.0

    def safe_int(v):
        return int(v) if v is not None else 0

    # 내림차순 정렬 인덱스 → rank (1이 최고)
    rating_sorted = sorted(range(n), key=lambda i: safe_float(products[i].get("rating")), reverse=True)
    review_sorted = sorted(range(n), key=lambda i: safe_int(products[i].get("review_count")), reverse=True)

    rating_rank = [0] * n
    review_rank = [0] * n
    for rank, idx in enumerate(rating_sorted, start=1):
        rating_rank[idx] = rank
    for rank, idx in enumerate(review_sorted, start=1):
        review_rank[idx] = rank

    avg_ranks = [(rating_rank[i] + review_rank[i]) / 2 for i in range(n)]
    top_indices = sorted(range(n), key=lambda i: avg_ranks[i])[:5]

    return [products[i] for i in top_indices]
