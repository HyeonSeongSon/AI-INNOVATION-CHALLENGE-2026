from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
import asyncio
import httpx
from pathlib import Path
from typing import Annotated, Optional, Literal
from pydantic import BaseModel, Field

from ...config.settings import settings
from ...core.auth import UserContext
from ...core.auth_utils import create_user_assertion
from ...core.http_client_registry import register
from .utils.ranking import rank_and_top5
from .utils.formatters import (
    format_get_all_personas,
    format_search_personas_by_text,
    format_get_persona_by_id,
    format_products_by_tag,
    format_products_by_brand,
    format_get_all_brands,
    format_get_all_categories,
    format_get_all_message_types,
)

DB_API_BASE_URL = settings.database_api_url + "/api"

_http_client: Optional[httpx.AsyncClient] = None


def init_search_http_client() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_default),
        headers={"X-Internal-Token": settings.internal_token},
    )
    register(_http_client)


def _get_http_client() -> httpx.AsyncClient:
    if _http_client is None or _http_client.is_closed:
        raise RuntimeError(
            "Search HTTP client not initialized — "
            "call init_search_http_client() in lifespan before handling requests"
        )
    return _http_client


def _make_user_assertion(user_id: str | None, role: str) -> str | None:
    if not user_id:
        return None
    return create_user_assertion(
        UserContext(user_id=user_id, role=role, email="", auth_method="jwt")
    )

# ============================================================
# 로컬 데이터 파일 로드 (ToDo: DB에서 호출하도록 변경)
# ============================================================

_DATA_DIR = Path(__file__).parents[4] / "data"

def _load_json(filename: str) -> dict:
    import json
    with open(_DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Tools
# ============================================================

@tool
async def get_all_personas(config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    데이터베이스에 저장된 모든 페르소나 목록을 조회합니다.
    사용자가 페르소나 목록을 보여달라고 하거나, 어떤 페르소나가 있는지 물어볼 때 사용하세요.
    """
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    role = configurable.get("role", "user")
    try:
        client = _get_http_client()
        assertion = _make_user_assertion(user_id, role)
        extra_headers = {"X-User-Assertion": assertion} if assertion else {}
        response = await client.post(
            f"{DB_API_BASE_URL}/personas/list",
            json={"page": 1, "page_size": 200},
            headers=extra_headers,
        )
        response.raise_for_status()
        personas = response.json().get("items", [])

    except httpx.HTTPStatusError:
        return "페르소나 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    except httpx.RequestError:
        return "DB API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

    if not personas:
        return "현재 등록된 페르소나가 없습니다."

    return format_get_all_personas(personas)



@tool
async def get_products_by_tag(tag: str) -> str:
    """
    상품 소분류(sub_tag)를 입력하면 해당 종류의 상품 중 인기 상위 5개를 조회합니다.
    별점과 리뷰수의 평균 순위가 높은 순으로 반환합니다.
    예시 태그: '에센스&세럼', '크림', '선크림', '마스크&팩', '클렌징폼', '샴푸', '에센스&세럼&오일'
    정확한 소분류 목록은 get_all_categories 툴로 먼저 확인하세요.
    사용자가 특정 상품 종류를 물어볼 때 사용하세요.
    """
    try:
        client = _get_http_client()
        response = await client.post(
            f"{DB_API_BASE_URL}/products/by-tag",
            json={"tag": tag, "page": 1, "page_size": 200}
        )
        response.raise_for_status()
        products = response.json().get("items", [])

    except httpx.HTTPStatusError:
        return "상품 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    except httpx.RequestError:
        return "DB API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

    if not products:
        return f"'{tag}' 태그에 해당하는 상품이 없습니다."

    products = rank_and_top5(products)
    return format_products_by_tag(tag, products)


@tool
async def get_products_by_brand(brand: str) -> str:
    """
    브랜드명을 입력하면 해당 브랜드의 상품 중 인기 상위 5개를 조회합니다.
    별점과 리뷰수의 평균 순위가 높은 순으로 반환합니다.
    사용자가 특정 브랜드의 상품을 물어볼 때 사용하세요.
    예시: '설화수', '헤라', '이니스프리', '라네즈'
    """
    try:
        client = _get_http_client()
        response = await client.post(
            f"{DB_API_BASE_URL}/products/by-brand",
            json={"brand": brand, "page": 1, "page_size": 200}
        )
        response.raise_for_status()
        products = response.json().get("items", [])

    except httpx.HTTPStatusError:
        return "상품 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    except httpx.RequestError:
        return "DB API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

    if not products:
        return f"'{brand}' 브랜드에 해당하는 상품이 없습니다."

    products = rank_and_top5(products)
    return format_products_by_brand(brand, products)


@tool
async def get_persona_by_id(persona_id: str, config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    특정 페르소나 ID의 모든 상세 정보를 조회합니다.
    페르소나 ID(예: PERSONA_001)를 알고 있을 때, 해당 페르소나의 전체 프로필을
    확인하고 싶을 때 사용하세요.
    """
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    role = configurable.get("role", "user")
    try:
        client = _get_http_client()
        response = await client.post(
            f"{DB_API_BASE_URL}/personas/get",
            json={"persona_id": persona_id, "user_id": user_id, "role": role}
        )
        response.raise_for_status()
        p = response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"해당 ID의 페르소나를 찾을 수 없습니다: {persona_id}"
        if e.response.status_code == 403:
            return f"해당 페르소나에 접근할 권한이 없습니다: {persona_id}"
        return "페르소나 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    except httpx.RequestError:
        return "DB API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

    return format_get_persona_by_id(p)


@tool
async def get_all_brands() -> str:
    """
    현재 서비스에서 제공 중인 브랜드 목록을 반환합니다.
    사용자가 어떤 브랜드가 있는지 물어보거나, get_products_by_brand 호출 전에
    유효한 브랜드명을 확인할 때 사용하세요.
    """
    brands = (await asyncio.to_thread(_load_json, "brands.json")).get("brands", [])
    if not brands:
        return "등록된 브랜드가 없습니다."
    return format_get_all_brands(brands)


@tool
async def get_all_categories() -> str:
    """
    현재 서비스에서 제공 중인 상품 종류(카테고리) 목록을 반환합니다.
    사용자가 어떤 상품 종류가 있는지 물어보거나, get_products_by_tag 호출 전에
    유효한 카테고리명을 확인할 때 사용하세요.
    """
    categories = (await asyncio.to_thread(_load_json, "category.json")).get("sub_tags", [])
    if not categories:
        return "등록된 상품 종류가 없습니다."
    return format_get_all_categories(categories)


@tool
async def get_all_message_types() -> str:
    """
    CRM 메시지 생성 시 사용할 수 있는 메시지 타입(목적) 목록과 각 설명을 반환합니다.
    사용자가 어떤 메시지 타입이 있는지 물어볼 때 사용하세요.
    """
    purposes = (await asyncio.to_thread(_load_json, "purposes.json")).get("purposes", {})
    if not purposes:
        return "등록된 메시지 타입이 없습니다."
    return format_get_all_message_types(purposes)


# ============================================================
# Structured Output 기반 페르소나 검색
# ============================================================

class PersonaSearchFilter(BaseModel):
    gender: Optional[str] = Field(None, description="성별: '남자' 또는 '여자'")
    age_min: Optional[int] = Field(None, description="최소 나이 (포함)")
    age_max: Optional[int] = Field(None, description="최대 나이 (포함)")
    skin_type: Optional[list[str]] = Field(None, description="피부 타입 (AND 조건). 예: ['지성', '트러블성']")
    concerns: Optional[list[str]] = Field(None, description="피부/헤어 고민 (AND 조건). 예: ['모공', '주름']")
    personal_color: Optional[str] = Field(None, description="퍼스널 컬러: '웜톤', '쿨톤', '웜스프링', '웜오텀', '쿨썸머', '쿨윈터'")
    lifestyle_values: Optional[list[str]] = Field(None, description="가치관 (AND 조건). 예: ['비건', '친환경']")
    stress_level: Optional[str] = Field(None, description="스트레스 수준: '낮음', '보통', '높음'")
    price_sensitivity: Optional[str] = Field(None, description="가격 민감도: '가성비중시', '프리미엄선호', '무관'")
    preferred_ingredients: Optional[list[str]] = Field(None, description="선호 성분 (AND 조건). 예: ['히알루론산', '레티놀']")
    avoided_ingredients: Optional[list[str]] = Field(None, description="기피 성분 (AND 조건). 예: ['알코올', '파라벤']")
    occupation: Optional[str] = Field(None, description="직업. 예: '마케터', '학생'")
    beauty_interests: Optional[list[str]] = Field(None, description="관심 뷰티 카테고리. 예: ['스킨케어', '헤어']")
    shopping_style: Optional[list[str]] = Field(None, description="쇼핑 스타일. 예: ['충동구매형', '신중형']")
    preferred_brands: Optional[list[str]] = Field(None, description="선호 브랜드 (기본 AND). 예: ['설화수', '이니스프리']")
    avoided_brands: Optional[list[str]] = Field(None, description="기피 브랜드 (기본 AND). 예: ['더페이스샵']")
    preferred_scents: Optional[list[str]] = Field(None, description="선호 향 (기본 AND). 예: ['플로럴', '우디']")
    preferred_colors: Optional[list[str]] = Field(None, description="선호 색상 (기본 AND). 예: ['코랄', '핑크']")
    preferred_texture: Optional[list[str]] = Field(None, description="선호 제형 (기본 AND). 예: ['젤', '크림']")
    hair_type: Optional[list[str]] = Field(None, description="모발 타입 (기본 AND). 예: ['건성', '손상모']")
    skincare_routine: Optional[list[str]] = Field(None, description="스킨케어 루틴 (기본 AND). 예: ['토너', '에센스']")
    main_environment: Optional[list[str]] = Field(None, description="주 활동 환경 (기본 AND). 예: ['실내', '에어컨']")
    purchase_decision_factors: Optional[list[str]] = Field(None, description="구매 결정 요인 (기본 AND). 예: ['성분', '브랜드신뢰']")
    pets: Optional[list[str]] = Field(None, description="반려동물 (기본 AND). 예: ['강아지', '고양이']")
    shade_number_min: Optional[int] = Field(None, description="파운데이션 쉐이드 최소값 (포함)")
    shade_number_max: Optional[int] = Field(None, description="파운데이션 쉐이드 최대값 (포함)")
    avg_sleep_hours_min: Optional[int] = Field(None, description="평균 수면 시간 최소값")
    avg_sleep_hours_max: Optional[int] = Field(None, description="평균 수면 시간 최대값")
    daily_screen_hours_min: Optional[int] = Field(None, description="일일 스크린 시간 최소값")
    daily_screen_hours_max: Optional[int] = Field(None, description="일일 스크린 시간 최대값")
    array_modes: dict[str, Literal["all", "any"]] = Field(
        default_factory=dict,
        description=(
            "배열 필드별 매칭 방식. 기본값 'all'(AND/@>). "
            "'any'로 설정하면 OR(&&). "
            "예: {\"skin_type\": \"any\"} → 지성 OR 복합성. "
            "명시하지 않은 필드는 모두 'all'(AND)."
        )
    )
    limit: int = Field(10, ge=1, le=20, description="반환할 최대 결과 수 (기본 10, 최대 20)")


@tool(args_schema=PersonaSearchFilter)
async def search_personas_by_filter(
    gender=None, age_min=None, age_max=None,
    skin_type=None, concerns=None, personal_color=None,
    lifestyle_values=None, stress_level=None, price_sensitivity=None,
    preferred_ingredients=None, avoided_ingredients=None,
    occupation=None, beauty_interests=None, shopping_style=None,
    preferred_brands=None, limit=10,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    구조화된 조건으로 페르소나를 검색합니다.
    피부 타입, 피부 고민, 퍼스널 컬러, 가치관, 나이대, 직업, 쇼핑 스타일,
    선호/기피 성분, 가격 민감도 등 구체적인 속성 조건이 있을 때 사용하세요.
    구체적인 속성 조건이 있을 때 이 함수를 사용하세요.
    """
    configurable = (config or {}).get("configurable", {})
    f = PersonaSearchFilter(
        gender=gender, age_min=age_min, age_max=age_max,
        skin_type=skin_type, concerns=concerns, personal_color=personal_color,
        lifestyle_values=lifestyle_values, stress_level=stress_level,
        price_sensitivity=price_sensitivity,
        preferred_ingredients=preferred_ingredients,
        avoided_ingredients=avoided_ingredients,
        occupation=occupation, beauty_interests=beauty_interests,
        shopping_style=shopping_style, preferred_brands=preferred_brands,
        limit=limit,
    )
    payload = {
        **f.model_dump(),
        "user_id": configurable.get("user_id"),
        "role": configurable.get("role", "user"),
    }
    try:
        client = _get_http_client()
        assertion = _make_user_assertion(configurable.get("user_id"), configurable.get("role", "user"))
        extra_headers = {"X-User-Assertion": assertion} if assertion else {}
        response = await client.post(
            f"{DB_API_BASE_URL}/personas/filter",
            json=payload,
            headers=extra_headers,
        )
        response.raise_for_status()
        rows = response.json()
    except httpx.HTTPStatusError:
        return "페르소나 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    except httpx.RequestError:
        return "DB API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."

    if not rows:
        return "조건에 맞는 페르소나가 없습니다."
    return format_search_personas_by_text(rows)
