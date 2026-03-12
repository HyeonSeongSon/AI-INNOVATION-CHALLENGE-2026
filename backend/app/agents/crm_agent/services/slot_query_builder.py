from typing import List, Set


_SLOT_ORDER = [
    "slot1_core",
    "slot2_function",
    "slot3_context",
    "slot4_texture",
    "slot5_values",
]


def validate_and_build(extracted: dict) -> List[str]:
    """
    LLM이 반환한 슬롯 키워드 dict를 검증·조립해 검색 쿼리 리스트로 변환.

    벡터 DB 시맨틱 검색 기반이므로 exact match 필터 없이 페르소나 기반 자유 생성 키워드를 그대로 사용.

    처리 순서:
    1) 슬롯 간 중복 제거 (cross-slot deduplication)
    2) 토큰 수 제한 (카테고리 제외 키워드 최대 6개)
    3) 키워드 2개 미만 슬롯 → 해당 쿼리 생략

    Args:
        extracted: LLM이 반환한 슬롯 키워드 dict
                   {"category": str, "slot1_core": [...], ..., "slot5_values": [...]}
        category_type: 카테고리 대분류 (현재 미사용, 하위 호환성 유지)

    Returns:
        List[str]: 슬롯별 조립된 검색 쿼리 (최대 5개)
    """
    category = extracted.get("category", "")

    seen: Set[str] = set()
    queries: List[str] = []

    for slot_key in _SLOT_ORDER:
        keywords: List[str] = list(extracted.get(slot_key, []))

        # 1) 슬롯 간 중복 제거
        keywords = [k for k in keywords if k not in seen]
        seen.update(keywords)

        # 2) 토큰 수 제한
        keywords = keywords[:6]

        # 3) 최소 키워드 수 미달 → 생략
        if len(keywords) < 2:
            continue

        queries.append(f"{category} {' '.join(keywords)}")

    return queries
