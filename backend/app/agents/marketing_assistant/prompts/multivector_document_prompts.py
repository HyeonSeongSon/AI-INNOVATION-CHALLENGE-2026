"""
멀티벡터 문서 생성 — 그룹 라우팅 + 프롬프트 통합 빌더

카테고리/태그 → 그룹(A~G) 매핑 후 해당 그룹 프롬프트를 호출한다.
"""

import json

from .prompts_group_a import build_group_a_prompt
from .prompts_group_b import build_group_b_prompt
from .prompts_group_c import build_group_c_prompt
from .prompts_group_d import build_group_d_prompt
from .prompts_group_e import build_group_e_prompt
from .prompts_group_f import build_group_f_prompt
from .prompts_group_g import build_group_g_prompt

# ──────────────────────────────────────────────────────
# 그룹별 필드 카운트 (정확히 이 수만큼 생성되어야 유효)
# ──────────────────────────────────────────────────────
GROUP_REQUIRED_COUNTS: dict[str, dict[str, int]] = {
    "A": {"combined": 6, "function_desc": 5, "attribute_desc": 3, "target_user": 6, "spec_feature": 2},
    "B": {"combined": 5, "function_desc": 4, "attribute_desc": 5, "target_user": 3, "spec_feature": 2},
    "C": {"combined": 7, "function_desc": 3, "attribute_desc": 4, "target_user": 3, "spec_feature": 1},
    "D": {"combined": 5, "function_desc": 5, "attribute_desc": 5, "target_user": 3, "spec_feature": 4},
    "E": {"combined": 5, "function_desc": 5, "attribute_desc": 2, "target_user": 5, "spec_feature": 3},
    "F": {"combined": 4, "function_desc": 3, "attribute_desc": 4, "target_user": 2, "spec_feature": 1},
    "G": {"combined": 5, "function_desc": 4, "attribute_desc": 4, "target_user": 3, "spec_feature": 2},
}

_MULTIVECTOR_FIELDS = list(next(iter(GROUP_REQUIRED_COUNTS.values())).keys())

# ──────────────────────────────────────────────────────
# 카테고리/태그 → 그룹 라우팅
# ──────────────────────────────────────────────────────

def get_multivector_group(main_category: str, tag: str, sub_tag: str = "") -> str:
    """
    카테고리와 태그 조합을 멀티벡터 그룹(A~G)으로 변환한다.

    Args:
        main_category: 최상위 카테고리 (예: "스킨케어")
        tag:           중분류 태그     (예: "클렌징")
        sub_tag:       세부 서브태그   (예: "입욕제/배쓰밤") — 향수/바디 엣지 케이스에 사용

    Returns:
        "A" | "B" | "C" | "D" | "E" | "F" | "G"

    Raises:
        ValueError: 지원하지 않는 main_category
    """
    if main_category == "스킨케어":
        return "A"

    if main_category == "색조":
        return "B"

    if main_category == "이너뷰티":
        return "E"

    if main_category == "향수/바디":
        if tag in {"향수", "홈프래그런스"}:
            return "C"
        if tag == "바디케어" and sub_tag == "입욕제/배쓰밤":
            return "C"
        return "A"

    if main_category == "헤어":
        if tag in {"스타일링", "헤어컬러"}:
            return "G"
        return "A"  # 세정, 모발케어, 두피케어 → A

    if main_category == "생활도구":
        if tag == "생활가전":
            return "D"
        return "F"  # 용기&수저 등

    if main_category == "뷰티툴":
        if tag in {"헤어기기", "마사지/전동케어", "피부관리", "기타디바이스"}:
            return "D"
        return "F"  # 메이크업툴, 브러쉬, 소품/도구, 수동마사지도구, 뷰티툴케어

    raise ValueError(
        f"지원하지 않는 카테고리: '{main_category}'. "
        f"지원 목록: 스킨케어, 색조, 이너뷰티, 향수/바디, 헤어, 생활도구, 뷰티툴"
    )


# ──────────────────────────────────────────────────────
# 그룹별 프롬프트 빌더 맵
# ──────────────────────────────────────────────────────

_GROUP_PROMPT_BUILDERS = {
    "A": build_group_a_prompt,
    "B": build_group_b_prompt,
    "C": build_group_c_prompt,
    "D": build_group_d_prompt,
    "E": build_group_e_prompt,
    "F": build_group_f_prompt,
    "G": build_group_g_prompt,
}


# ──────────────────────────────────────────────────────
# 통합 빌더
# ──────────────────────────────────────────────────────

def build_multivector_prompt(
    structured: dict,
    main_category: str,
    tag: str,
    sub_tag: str = "",
) -> tuple[str, str]:
    """
    구조화된 상품 정보를 멀티벡터 프롬프트로 변환한다.

    Args:
        structured:    create_product_document()가 반환한 구조화 dict
        main_category: 최상위 카테고리
        tag:           중분류 태그
        sub_tag:       세부 서브태그 (옵션)

    Returns:
        (prompt_str, group_id) — LLM에 전달할 프롬프트와 사용된 그룹 ID
    """
    group = get_multivector_group(main_category, tag, sub_tag)
    product_document = json.dumps(structured, ensure_ascii=False, indent=2)
    prompt = _GROUP_PROMPT_BUILDERS[group](product_document)
    return prompt, group
