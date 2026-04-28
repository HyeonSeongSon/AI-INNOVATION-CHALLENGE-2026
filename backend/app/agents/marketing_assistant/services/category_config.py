"""
카테고리/태그 설정 — 유효성 검사, extra_category 매핑, 프롬프트 빌더 매핑

product_registration.py의 서비스 로직과 분리해서 관리한다.
"""
import json
import functools
import pathlib

from backend.app.agents.marketing_assistant.prompts.document_skin_care_prompts import (
    build_skin_care_category_product_prompt,
)
from backend.app.agents.marketing_assistant.prompts.document_hair_prompt import (
    build_hair_category_product_prompt,
)
from backend.app.agents.marketing_assistant.prompts.document_color_prompts import (
    build_color_tone_category_product_prompts,
)
from backend.app.agents.marketing_assistant.prompts.document_fragrance_and_body_prompt import (
    build_fragrance_body_category_product_prompt,
)
from backend.app.agents.marketing_assistant.prompts.document_inner_beauty_prompt import (
    build_inner_beauty_category_product_prompt,
)
from backend.app.agents.marketing_assistant.prompts.document_living_supplies_prompt import (
    build_daily_goods_product_prompt,
)
from backend.app.agents.marketing_assistant.prompts.document_beauty_tool_prompt import (
    build_beauty_device_category_product_prompt,
)

# ──────────────────────────────────────────────────────
# category.json 로더
# ──────────────────────────────────────────────────────

_CATEGORY_JSON_PATH = pathlib.Path(__file__).parents[5] / "data" / "category.json"


@functools.lru_cache(maxsize=1)
def _load_category_json() -> dict:
    with open(_CATEGORY_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────
# 유효성 검사
# ──────────────────────────────────────────────────────

def is_valid_category_tag(main_category: str, tag: str) -> bool:
    """category.json 기준으로 (main_category, tag) 조합이 유효한지 확인."""
    categories = _load_category_json().get("categories", {})
    cat_data = categories.get(main_category)
    if cat_data is None:
        return False
    return tag in cat_data


def classify_product_batch(
    items: list[dict],
    *,
    category_key: str = "main_category",
    tag_key: str = "tag",
) -> tuple[list[dict], list[dict]]:
    """
    items를 category.json 기준으로 유효/무효로 분류한다.

    Returns:
        (valid_items, invalid_items)
    """
    valid: list[dict] = []
    invalid: list[dict] = []
    for item in items:
        if is_valid_category_tag(item.get(category_key, ""), item.get(tag_key, "")):
            valid.append(item)
        else:
            invalid.append(item)
    return valid, invalid


# ──────────────────────────────────────────────────────
# 태그 → extra_category 매핑
# ──────────────────────────────────────────────────────

_TAG_TO_EXTRA_CATEGORY: dict[str, dict[str, str]] = {
    "스킨케어": {
        "클렌징":       "cleansing",
        "기초케어":     "base_care",
        "특수케어":     "special_care",
        "선케어":       "sun_care",
        "스킨케어세트": "skincare_set",
    },
    "헤어": {
        "세정":     "hair_cleansing",
        "모발케어": "hair_treatment",
        "두피케어": "scalp_care",
        "스타일링": "hair_styling_",
        "헤어컬러": "hair_color",
    },
    "색조": {
        "베이스메이크업": "base_makeup",
        "립메이크업":     "lip_makeup",
        "아이메이크업":   "eye_makeup",
        "치크/쉐딩":     "cheek",
        "키트&팔레트":   "palette",
    },
    "향수/바디": {
        "향수":         "fragrance",
        "바디세정":     "body_cleansing",
        "여성청결제":   "feminine_care",
        "바디케어":     "body_care",
        "홈프래그런스": "home_fragrance",
    },
    "이너뷰티": {
        "기능성이너뷰티": "functional_subtags",
        "이너뷰티푸드":   "food_subtags",
    },
    "생활도구": {
        "생활가전":  "home_appliance",
        "용기&수저": "tableware",
    },
    "뷰티툴": {
        "메이크업툴":      "makeup_tool",
        "브러쉬":          "brush",
        "소품/도구":       "beauty_accessory",
        "헤어기기":        "beauty_device_extra",
        "피부관리":        "beauty_device_extra",
        "기타디바이스":    "beauty_device_extra",
        "마사지/전동케어": "beauty_device_extra",
        "수동마사지도구":  "manual_massage_tool",
        "뷰티툴케어":      "beauty_tool_care",
    },
}


def resolve_extra_category(main_category: str, tag: str) -> str:
    """태그를 extra_category 문자열로 변환한다."""
    tag_map = _TAG_TO_EXTRA_CATEGORY.get(main_category)
    if tag_map is None:
        raise ValueError(
            f"지원하지 않는 카테고리: '{main_category}'. "
            f"지원 목록: {list(_TAG_TO_EXTRA_CATEGORY.keys())}"
        )
    extra_category = tag_map.get(tag)
    if extra_category is None:
        raise ValueError(
            f"'{main_category}'에 존재하지 않는 태그: '{tag}'. "
            f"지원 태그: {list(tag_map.keys())}"
        )
    return extra_category


# ──────────────────────────────────────────────────────
# 카테고리 → 프롬프트 빌더 매핑
# ──────────────────────────────────────────────────────

PROMPT_BUILDERS: dict = {
    "스킨케어": build_skin_care_category_product_prompt,
    "헤어":     build_hair_category_product_prompt,
    "색조":     build_color_tone_category_product_prompts,
    "향수/바디": build_fragrance_body_category_product_prompt,
    "이너뷰티": build_inner_beauty_category_product_prompt,
    "생활도구": build_daily_goods_product_prompt,
    "뷰티툴":   build_beauty_device_category_product_prompt,
}
