from langchain_core.tools import tool
import httpx
import os
import yaml
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from ...core.llm_factory import get_llm
from langchain_core.messages import HumanMessage

from .prompts.search_tools_prompt import build_search_personas_by_text_prompt
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

DB_API_BASE_URL = os.getenv("DATABASE_API_URL", "http://localhost:8020") + "/api"

# ============================================================
# 로컬 데이터 파일 로드 (ToDo: DB에서 호출하도록 변경)
# ============================================================

_DATA_DIR = Path(__file__).parents[4] / "data"

def _load_json(filename: str) -> dict:
    import json
    with open(_DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)

# ============================================================
# 외부 파일에서 스키마 로드
# ============================================================

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "persona_table_schema.yaml"
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _PERSONA_SCHEMA = yaml.safe_load(_f)["schemas"]["persona_table_schema"]


# ============================================================
# Tools
# ============================================================

@tool
async def get_all_personas() -> str:
    """
    데이터베이스에 저장된 모든 페르소나 목록을 조회합니다.
    사용자가 페르소나 목록을 보여달라고 하거나, 어떤 페르소나가 있는지 물어볼 때 사용하세요.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{DB_API_BASE_URL}/personas/list")
        response.raise_for_status()
        personas = response.json()

    if not personas:
        return "현재 등록된 페르소나가 없습니다."

    return format_get_all_personas(personas)


@tool
async def search_personas_by_text(natural_query: str) -> str:
    """
    자연어 조건으로 페르소나를 검색합니다.
    피부 타입, 피부 고민, 퍼스널 컬러, 가치관, 나이대, 직업, 쇼핑 스타일 등
    구체적인 속성 조건이 있을 때 사용하세요.
    예시: '지성 피부이면서 비건 가치관인 20대', '모공 고민이 있는 쿨톤 여성',
          '히알루론산을 선호하고 알코올을 기피하는 페르소나', '스트레스가 높은 직장인'
    """
    # LLM으로 SQL 생성 (temperature=0으로 결정론적 SQL 생성)
    model_name = os.getenv("CHATGPT_MODEL_NAME", "gpt-4o-mini")
    llm = get_llm(model_name, temperature=0)

    messages = build_search_personas_by_text_prompt(
        schema=_PERSONA_SCHEMA,
        natural_query=natural_query
    )
    sql_response = await llm.ainvoke(messages)
    generated_sql = sql_response.content.strip()

    # 마크다운 코드블록 제거 (LLM이 ```sql ... ``` 형식으로 반환하는 경우 방어)
    if generated_sql.startswith("```"):
        lines = generated_sql.split("\n")
        generated_sql = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    # DB API 서버에 SQL 실행 요청
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{DB_API_BASE_URL}/personas/query",
                json={"sql_query": generated_sql}
            )
            response.raise_for_status()
            rows = response.json()

    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        return f"페르소나 검색 중 오류가 발생했습니다: {error_detail}\n생성된 SQL: {generated_sql}"

    except httpx.RequestError as e:
        return f"DB API 서버 연결 실패: {str(e)}"

    # 결과 포맷팅
    if not rows:
        return f"조건에 맞는 페르소나가 없습니다.\n검색 조건: {natural_query}\n실행된 SQL: {generated_sql}"

    return format_search_personas_by_text(rows)


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
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{DB_API_BASE_URL}/products/by-tag",
                json={"tag": tag}
            )
            response.raise_for_status()
            products = response.json()

    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        return f"상품 조회 중 오류가 발생했습니다: {error_detail}"

    except httpx.RequestError as e:
        return f"DB API 서버 연결 실패: {str(e)}"

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
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{DB_API_BASE_URL}/products/by-brand",
                json={"brand": brand}
            )
            response.raise_for_status()
            products = response.json()

    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        return f"상품 조회 중 오류가 발생했습니다: {error_detail}"

    except httpx.RequestError as e:
        return f"DB API 서버 연결 실패: {str(e)}"

    if not products:
        return f"'{brand}' 브랜드에 해당하는 상품이 없습니다."

    products = rank_and_top5(products)
    return format_products_by_brand(brand, products)


@tool
async def get_persona_by_id(persona_id: str) -> str:
    """
    특정 페르소나 ID의 모든 상세 정보를 조회합니다.
    페르소나 ID(예: PERSONA_001)를 알고 있을 때, 해당 페르소나의 전체 프로필을
    확인하고 싶을 때 사용하세요.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{DB_API_BASE_URL}/personas/get",
                json={"persona_id": persona_id}
            )
            response.raise_for_status()
            p = response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"해당 ID의 페르소나를 찾을 수 없습니다: {persona_id}"
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        return f"페르소나 조회 중 오류가 발생했습니다: {error_detail}"

    except httpx.RequestError as e:
        return f"DB API 서버 연결 실패: {str(e)}"

    return format_get_persona_by_id(p)


@tool
def get_all_brands() -> str:
    """
    현재 서비스에서 제공 중인 브랜드 목록을 반환합니다.
    사용자가 어떤 브랜드가 있는지 물어보거나, get_products_by_brand 호출 전에
    유효한 브랜드명을 확인할 때 사용하세요.
    """
    brands = _load_json("brands.json").get("brands", [])
    if not brands:
        return "등록된 브랜드가 없습니다."
    return format_get_all_brands(brands)


@tool
def get_all_categories() -> str:
    """
    현재 서비스에서 제공 중인 상품 종류(카테고리) 목록을 반환합니다.
    사용자가 어떤 상품 종류가 있는지 물어보거나, get_products_by_tag 호출 전에
    유효한 카테고리명을 확인할 때 사용하세요.
    """
    categories = _load_json("category.json").get("sub_tags", [])
    if not categories:
        return "등록된 상품 종류가 없습니다."
    return format_get_all_categories(categories)


@tool
def get_all_message_types() -> str:
    """
    CRM 메시지 생성 시 사용할 수 있는 메시지 타입(목적) 목록과 각 설명을 반환합니다.
    사용자가 어떤 메시지 타입이 있는지 물어볼 때 사용하세요.
    """
    purposes = _load_json("purposes.json").get("purposes", {})
    if not purposes:
        return "등록된 메시지 타입이 없습니다."
    return format_get_all_message_types(purposes)


# ============================================================
# Structured Output 기반 페르소나 검색
# ============================================================

class PersonaSearchFilter(BaseModel):
    gender: Optional[str] = Field(None, description="성별: '남성' 또는 '여성'")
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
    preferred_brands: Optional[list[str]] = Field(None, description="선호 브랜드. 예: ['설화수', '이니스프리']")
    limit: int = Field(10, description="반환할 최대 결과 수 (기본 10, 최대 20)")


def _build_persona_filter_sql(f: PersonaSearchFilter) -> str:
    conditions = []

    if f.gender:
        conditions.append(f"gender = '{f.gender}'")
    if f.age_min is not None:
        conditions.append(f"age >= {f.age_min}")
    if f.age_max is not None:
        conditions.append(f"age <= {f.age_max}")
    if f.skin_type:
        arr = ", ".join(f"'{v}'" for v in f.skin_type)
        conditions.append(f"skin_type @> ARRAY[{arr}]")
    if f.concerns:
        arr = ", ".join(f"'{v}'" for v in f.concerns)
        conditions.append(f"concerns @> ARRAY[{arr}]")
    if f.personal_color:
        conditions.append(f"personal_color = '{f.personal_color}'")
    if f.lifestyle_values:
        arr = ", ".join(f"'{v}'" for v in f.lifestyle_values)
        conditions.append(f"lifestyle_values @> ARRAY[{arr}]")
    if f.stress_level:
        conditions.append(f"stress_level = '{f.stress_level}'")
    if f.price_sensitivity:
        conditions.append(f"price_sensitivity = '{f.price_sensitivity}'")
    if f.preferred_ingredients:
        arr = ", ".join(f"'{v}'" for v in f.preferred_ingredients)
        conditions.append(f"preferred_ingredients @> ARRAY[{arr}]")
    if f.avoided_ingredients:
        arr = ", ".join(f"'{v}'" for v in f.avoided_ingredients)
        conditions.append(f"avoided_ingredients @> ARRAY[{arr}]")
    if f.occupation:
        conditions.append(f"occupation = '{f.occupation}'")
    if f.beauty_interests:
        arr = ", ".join(f"'{v}'" for v in f.beauty_interests)
        conditions.append(f"beauty_interests @> ARRAY[{arr}]")
    if f.shopping_style:
        arr = ", ".join(f"'{v}'" for v in f.shopping_style)
        conditions.append(f"shopping_style @> ARRAY[{arr}]")
    if f.preferred_brands:
        arr = ", ".join(f"'{v}'" for v in f.preferred_brands)
        conditions.append(f"preferred_brands @> ARRAY[{arr}]")

    limit = min(f.limit, 20)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return f"SELECT * FROM personas {where} LIMIT {limit}"


@tool(args_schema=PersonaSearchFilter)
async def search_personas_by_filter(
    gender=None, age_min=None, age_max=None,
    skin_type=None, concerns=None, personal_color=None,
    lifestyle_values=None, stress_level=None, price_sensitivity=None,
    preferred_ingredients=None, avoided_ingredients=None,
    occupation=None, beauty_interests=None, shopping_style=None,
    preferred_brands=None, limit=10,
) -> str:
    """
    구조화된 조건으로 페르소나를 검색합니다.
    피부 타입, 피부 고민, 퍼스널 컬러, 가치관, 나이대, 직업, 쇼핑 스타일,
    선호/기피 성분, 가격 민감도 등 구체적인 속성 조건이 있을 때 사용하세요.
    search_personas_by_text보다 이 함수를 우선 사용하세요.
    """
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
    sql = _build_persona_filter_sql(f)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{DB_API_BASE_URL}/personas/query",
                json={"sql_query": sql}
            )
            response.raise_for_status()
            rows = response.json()
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        return f"페르소나 검색 중 오류가 발생했습니다: {error_detail}"
    except httpx.RequestError as e:
        return f"DB API 서버 연결 실패: {str(e)}"

    if not rows:
        return "조건에 맞는 페르소나가 없습니다."
    return format_search_personas_by_text(rows)
