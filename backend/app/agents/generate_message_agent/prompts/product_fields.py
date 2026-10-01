"""
메시지 생성기가 받는 상품정보의 경계와 근거 규칙 상수.

- GENERATION_EXCLUDED_FIELDS: 생성 입력에서 빼는 시스템 필드. 상품 사실이 아니라 DB 운영 값이다.
  허용 목록이 아니라 제외 목록인 이유: 카테고리별 사실 필드(finish_type · sun_protection · spf 등)가 많아
  공통 필드만 남기면 정보가 빠진다. 판정기 · 피드백의 허용 필드(23개)와의 통일은 게이트 실험 뒤에 한다.
- POPULARITY_MIN_REVIEWS: 인기 · 선택 표현("많은 분들이 선택" 등)을 쓸 수 있는 리뷰 수 문턱.
  생성 프롬프트와 eval/generator_grounding 의 측정 정의가 이 한 값을 같이 쓴다.
"""

from typing import Any, Dict

GENERATION_EXCLUDED_FIELDS = frozenset({
    "product_id",
    "vectordb_id",
    "product_created_at",  # DB 등록 시각 — 출시일이 아니다
    "combined",
    "search_tags",
    "search_phrases",
})

POPULARITY_MIN_REVIEWS = 100

FIELD_GUIDE = f"""## 상품정보 필드 안내
- 별도의 출시일 · 판매량 · 판매 순위 필드는 없습니다. proof_points · value · summary · product_comment 에
  적힌 경우에만 그 문구대로 씁니다.
- 시험 · 인증 · 임상 · 수상은 proof_points · value 에 있는 것만 씁니다.
- rating · review_count 는 실제 리뷰 데이터입니다. 인기 · 선택을 말하려면 이 수치를 그대로 인용하고,
  review_count 가 {POPULARITY_MIN_REVIEWS}건 미만이고 판매 · 순위 문구도 없으면 인기 · 선택 표현을 쓰지 않습니다.
- sale_price · original_price · discount_rate 는 가격 정보이며 그대로 인용합니다.
- usage_context 는 사용 상황 · 방법입니다. 사용 시간 · 횟수 · 단계는 여기나 다른 필드에 적힌 경우에만 씁니다."""


def _is_empty(value: Any) -> bool:
    """빈 값은 None · "" · [] · {} 만 뜻한다. 0(discount_rate=0 · review_count=0)은 정보라 남긴다."""
    return value is None or (isinstance(value, (str, list, dict)) and len(value) == 0)


def generation_product_info(product: Dict[str, Any]) -> Dict[str, Any]:
    """생성 프롬프트에 넣을 상품정보 — 시스템 필드와 빈 값을 뺀다."""
    return {k: v for k, v in product.items() if k not in GENERATION_EXCLUDED_FIELDS and not _is_empty(v)}
