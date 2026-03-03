from langchain_core.tools import tool
import httpx
import os
import yaml
from pathlib import Path

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

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "persona_table_schema.yaml"
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
    상품종류(태그)를 입력하면 해당 종류의 상품 중 인기 상위 5개를 조회합니다.
    별점과 리뷰수의 평균 순위가 높은 순으로 반환합니다.
    예시 태그: '에센스&세럼&오일', '크림', '선케어', '마스크팩', '클렌징'
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
    categories = _load_json("categories.json").get("categories", [])
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
