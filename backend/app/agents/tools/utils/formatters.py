"""
tool 결과 포맷팅 유틸리티
각 tool 이름별로 포맷 함수를 정의합니다.
"""

from typing import Any


# ============================================================
# 페르소나 포맷터
# ============================================================

def format_get_all_personas(personas: list[dict[str, Any]]) -> str:
    """get_all_personas 툴 결과 포맷팅"""
    lines = [f"총 {len(personas)}명의 페르소나가 등록되어 있습니다.\n"]
    for p in personas:
        line = f"- [{p['persona_id']}] {p['name']}"
        if p.get("age") and p.get("gender"):
            line += f" ({p['age']}세, {p['gender']})"
        if p.get("occupation"):
            line += f" / {p['occupation']}"
        if p.get("skin_type"):
            line += f" / 피부타입: {', '.join(p['skin_type'])}"
        lines.append(line)
    return "\n".join(lines)


def format_search_personas_by_text(rows: list[dict[str, Any]]) -> str:
    """search_personas_by_text 툴 결과 포맷팅"""
    result_lines = [f"검색 결과: {len(rows)}명의 페르소나를 찾았습니다.\n"]
    for p in rows:
        line = f"- [{p.get('persona_id', 'N/A')}] {p.get('name', '이름 없음')}"
        if p.get("age") and p.get("gender"):
            line += f" ({p['age']}세, {p['gender']})"
        if p.get("occupation"):
            line += f" / {p['occupation']}"
        if p.get("skin_type"):
            skin = p["skin_type"] if isinstance(p["skin_type"], list) else [p["skin_type"]]
            line += f" / 피부타입: {', '.join(skin)}"
        if p.get("skin_concerns"):
            concerns = p["skin_concerns"] if isinstance(p["skin_concerns"], list) else [p["skin_concerns"]]
            line += f" / 고민: {', '.join(concerns)}"
        if p.get("personal_color"):
            line += f" / 퍼스널컬러: {p['personal_color']}"
        if p.get("values"):
            vals = p["values"] if isinstance(p["values"], list) else [p["values"]]
            line += f" / 가치관: {', '.join(vals)}"
        result_lines.append(line)
    return "\n".join(result_lines)


def _fmt_list(val) -> str | None:
    if not val:
        return None
    return ", ".join(val) if isinstance(val, list) else str(val)


def format_get_persona_by_id(p: dict[str, Any]) -> str:
    """get_persona_by_id 툴 결과 포맷팅"""
    sections = []

    basic = [f"[{p['persona_id']}] {p['name']}"]
    if p.get("age") and p.get("gender"):
        basic.append(f"{p['age']}세, {p['gender']}")
    if p.get("occupation"):
        basic.append(p["occupation"])
    sections.append("■ 기본정보\n  " + " / ".join(basic))

    skin_lines = []
    if _fmt_list(p.get("skin_type")):
        skin_lines.append(f"피부타입: {_fmt_list(p['skin_type'])}")
    if _fmt_list(p.get("skin_concerns")):
        skin_lines.append(f"피부고민: {_fmt_list(p['skin_concerns'])}")
    if p.get("personal_color"):
        shade = f" (셰이드: {p['shade_number']})" if p.get("shade_number") else ""
        skin_lines.append(f"퍼스널컬러: {p['personal_color']}{shade}")
    if skin_lines:
        sections.append("■ 피부정보\n  " + "\n  ".join(skin_lines))

    pref_lines = []
    if _fmt_list(p.get("preferred_colors")):
        pref_lines.append(f"선호 색상: {_fmt_list(p['preferred_colors'])}")
    if _fmt_list(p.get("preferred_ingredients")):
        pref_lines.append(f"선호 성분: {_fmt_list(p['preferred_ingredients'])}")
    if _fmt_list(p.get("avoided_ingredients")):
        pref_lines.append(f"기피 성분: {_fmt_list(p['avoided_ingredients'])}")
    if _fmt_list(p.get("preferred_scents")):
        pref_lines.append(f"선호 향: {_fmt_list(p['preferred_scents'])}")
    if _fmt_list(p.get("preferred_texture")):
        pref_lines.append(f"선호 텍스처: {_fmt_list(p['preferred_texture'])}")
    if pref_lines:
        sections.append("■ 선호도\n  " + "\n  ".join(pref_lines))

    life_lines = []
    if _fmt_list(p.get("values")):
        life_lines.append(f"가치관: {_fmt_list(p['values'])}")
    if p.get("skincare_routine"):
        life_lines.append(f"스킨케어 루틴: {p['skincare_routine']}")
    if p.get("main_environment"):
        life_lines.append(f"주요 환경: {p['main_environment']}")
    if p.get("pets"):
        life_lines.append(f"반려동물: {p['pets']}")
    if p.get("avg_sleep_hours") is not None:
        life_lines.append(f"평균 수면: {p['avg_sleep_hours']}시간")
    if p.get("stress_level"):
        life_lines.append(f"스트레스 수준: {p['stress_level']}")
    if p.get("digital_device_usage_time") is not None:
        life_lines.append(f"디지털 기기 사용: {p['digital_device_usage_time']}시간/일")
    if life_lines:
        sections.append("■ 라이프스타일\n  " + "\n  ".join(life_lines))

    shop_lines = []
    if p.get("shopping_style"):
        shop_lines.append(f"쇼핑 스타일: {p['shopping_style']}")
    if _fmt_list(p.get("purchase_decision_factors")):
        shop_lines.append(f"구매 결정 요인: {_fmt_list(p['purchase_decision_factors'])}")
    if shop_lines:
        sections.append("■ 쇼핑 성향\n  " + "\n  ".join(shop_lines))

    if p.get("persona_created_at"):
        sections.append(f"■ 생성일시: {p['persona_created_at']}")

    return "\n\n".join(sections)


# ============================================================
# 메타데이터 포맷터
# ============================================================

def format_get_all_brands(brands: list[str]) -> str:
    """get_all_brands 툴 결과 포맷팅"""
    return "제공 중인 브랜드 목록:\n" + "\n".join(f"- {b}" for b in brands)


def format_get_all_categories(categories: list[str]) -> str:
    """get_all_categories 툴 결과 포맷팅"""
    return "제공 중인 상품 종류 목록:\n" + "\n".join(f"- {c}" for c in categories)


def format_get_all_message_types(purposes: dict[str, str]) -> str:
    """get_all_message_types 툴 결과 포맷팅"""
    return "사용 가능한 메시지 타입 목록:\n" + "\n".join(
        f"- {name}: {desc}" for name, desc in purposes.items()
    )


# ============================================================
# 상품 포맷터
# ============================================================

def _format_product_item(i: int, p: dict[str, Any], show_brand: bool = True) -> str:
    """단일 상품 항목 포맷팅 (공통)"""
    if show_brand:
        line = f"{i}. [{p['product_id']}] {p.get('brand', '-')} - {p['product_name']}"
    else:
        line = f"{i}. [{p['product_id']}] {p['product_name']}"

    line += (
        f"\n   종류: {p.get('product_tag', '-')}"
        f" | 별점: {p.get('rating', '-')}"
        f" | 리뷰: {p.get('review_count', '-')}개"
    )
    line += f"\n   판매가: {p['sale_price']:,}원" if p.get('sale_price') else "\n   판매가: -"
    if p.get('product_comment'):
        line += f"\n   소개: {p['product_comment']}"
    if p.get('product_page_url'):
        line += f"\n   URL: {p['product_page_url']}"
    return line


def format_products_by_tag(tag: str, products: list[dict[str, Any]]) -> str:
    """get_products_by_tag 툴 결과 포맷팅"""
    lines = [f"[{tag}] 인기 상위 {len(products)}개 상품\n"]
    for i, p in enumerate(products, start=1):
        lines.append(_format_product_item(i, p, show_brand=True))
    return "\n\n".join(lines)


def format_products_by_brand(brand: str, products: list[dict[str, Any]]) -> str:
    """get_products_by_brand 툴 결과 포맷팅"""
    lines = [f"[{brand}] 인기 상위 {len(products)}개 상품\n"]
    for i, p in enumerate(products, start=1):
        lines.append(_format_product_item(i, p, show_brand=False))
    return "\n\n".join(lines)
