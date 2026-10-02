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


# 페르소나-상품 연결(persona_fit)의 근거 필드 분류. 스냅숏 필드는 카테고리별로 약 130종이라 허용 목록 대신
# 분류표로 둔다. 고민 연결(concern)의 근거는 evidence 만, 선호 일치(preference)는 evidence · style 을 허용하고,
# meta 는 근거로 쓰지 않는다. 표에 없는 필드는 evidence 로 보고 경고를 남긴다(persona_fit).
_META_FIELDS = (
    "product_id", "vectordb_id", "product_created_at", "combined", "search_tags", "search_phrases",
    "product_name", "brand", "category", "tag", "sub_tag", "rating", "review_count",
    "original_price", "discount_rate", "sale_price", "exclusive_product",
)
_STYLE_FIELDS = (
    "texture", "texture_feel", "finish_type", "absorption_speed", "greasy_feel", "residue_feel", "white_cast",
    "fragrance", "fragrance_level", "fragrance_family", "preferred_scents", "taste", "lather",
    "shade_info", "color_family", "preferred_colors", "personal_color", "skin_shades", "undertone",
    "lip_finish", "shadow_finish", "coverage", "pigmentation", "hold_level", "noise_level",
    # 향 노트 · 분위기 · 색 · 사용감 · 재질(선호 일치에는 쓰되 고민 연결의 근거는 아님)
    "top_note", "middle_note", "base_note", "mood", "season", "concentration", "color_type", "cheek_finish",
    "finish_variety", "application_texture", "bristle_feel", "lash_style", "volume_effect", "bath_color",
    "material", "handle_material", "stick_material", "tip_type", "size", "craftsmanship", "total_shade_count",
    "palette_categories",
)
FIELD_CLASS: Dict[str, str] = {**{f: "meta" for f in _META_FIELDS}, **{f: "style" for f in _STYLE_FIELDS}}
# evidence 로 확인한 필드(분류표 전수 점검에서 '빠진 키 0'을 보장하려고 명시한다)
_EVIDENCE_FIELDS = (
    "summary", "target_user", "key_benefits", "function_desc", "product_story", "attribute_desc", "highlight_keywords",
    "function", "attribute", "usage_context", "body_area", "value", "concern", "concerns", "target_tags",
    "function_tags", "attribute_tags", "product_comment", "ingredient", "proof_points", "preferred_ingredients",
    "avoided_ingredients", "skin_type", "suitable_for", "lifestyle_values", "care_product_type", "layering_order",
    "hair_type", "technology", "treatment_type", "rinse_off", "skin_feel_after", "power_source", "heat_protection",
    "moisture_level", "cleansing_strength", "wear_time", "hand_foot_concern", "scalp_type", "treatment_focus",
    "scalp_function", "device_type", "damage_level", "sun_protection", "skin_function", "lip_care_function",
    "key_nutrients", "function_claim", "appliance_type", "hair_function", "inner_product_type", "portability",
    "concentration_level", "daily_intake", "durability", "makeup_removal_level", "application_timing",
    "transfer_resistance", "hair_tool_spec", "usage_frequency", "intensity_levels", "leave_on_time", "capacity",
    "pa", "spf", "certification", "ph_level", "scalp_care_type", "brow_type", "is_functional", "hair_loss_function",
    "water_resistance", "longevity", "styling_type", "session_time", "caffeine", "tea_blend", "tea_product_type",
    "sun_filter_type", "cleansing_type", "slimming_function", "pore_function", "brewing_method", "runtime",
    "aluminum_free", "mascara_effect", "tool_type", "tool_function", "waterproof", "layering_compatible_types",
    "conditioner_function", "primer_function", "powder_type", "liner_type", "greasy_feel_level",
    # 시드 전수 점검(2026-10-01)에서 추가 — 효능 · 대상 · 구성 · 안전 · 기기 기능
    "accessory_type", "allergen_free", "ammonia_free", "antibacterial", "band_type", "bath_effect", "bristle_care",
    "bristle_type", "brush_area", "burn_time", "care_type", "cartridge_replaceable", "cheek_product_type",
    "color_durability", "compatible_tools", "deodorant_type", "exfoliation_type", "eye_concern", "feminine_function",
    "formulation_type", "free_of", "gray_coverage", "hair_condition_after", "humidity_resistance", "included_items",
    "kit_extras", "latex_free", "light_type", "massage_area", "massage_function", "massage_mode", "medical_certified",
    "over_makeup", "processing_time", "product_form", "product_type", "reapplication", "reusable", "scalp_safety",
    "scrub_ingredient", "set_concept", "shot_count", "skin_sensor", "snack_product_type", "soap_type",
    "tableware_type", "washable",
)
FIELD_CLASS.update({f: "evidence" for f in _EVIDENCE_FIELDS if f not in FIELD_CLASS})


def field_class(field: str) -> str | None:
    """분류표에 없으면 None(호출한 쪽이 evidence 로 보고 경고를 남긴다)."""
    return FIELD_CLASS.get(field)


def _is_empty(value: Any) -> bool:
    """빈 값은 None · "" · [] · {} 만 뜻한다. 0(discount_rate=0 · review_count=0)은 정보라 남긴다."""
    return value is None or (isinstance(value, (str, list, dict)) and len(value) == 0)


def generation_product_info(product: Dict[str, Any]) -> Dict[str, Any]:
    """생성 프롬프트에 넣을 상품정보 — 시스템 필드와 빈 값을 뺀다."""
    return {k: v for k, v in product.items() if k not in GENERATION_EXCLUDED_FIELDS and not _is_empty(v)}
