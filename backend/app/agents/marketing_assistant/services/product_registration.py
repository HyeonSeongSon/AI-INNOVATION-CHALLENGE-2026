import json
import asyncio
import base64
import io
from datetime import datetime
from uuid import uuid4
from typing import Union

import httpx
from PIL import Image
from langchain_core.messages import HumanMessage

from ....core.llm_factory import get_llm
from ....config.settings import Settings, settings
from ..prompts.multivector_document_prompts import (
    GROUP_REQUIRED_COUNTS,
    _MULTIVECTOR_FIELDS,
    build_multivector_prompt,
)
from .category_config import (
    _load_category_json,
    is_valid_category_tag,
    resolve_extra_category,
    PROMPT_BUILDERS as _PROMPT_BUILDERS,
)
from ....core.logging import get_logger

logger = get_logger("product_registration")

# ──────────────────────────────────────────────────────
# 이미지 처리 상수
# ──────────────────────────────────────────────────────
MAX_CHUNK_HEIGHT = 4000
CHUNK_OVERLAP    = 100
MAX_CHUNKS       = 10

# ──────────────────────────────────────────────────────
# 이미지 유틸
# ──────────────────────────────────────────────────────

async def _download_image(url: str) -> Image.Image:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": "https://www.amoremall.com/",
    }
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _split_image(image: Image.Image) -> list[Image.Image]:
    """세로 길이가 MAX_CHUNK_HEIGHT를 넘으면 청크로 분할, 아니면 그대로 반환."""
    width, height = image.size
    if height <= MAX_CHUNK_HEIGHT:
        return [image]

    chunks = []
    step = MAX_CHUNK_HEIGHT - CHUNK_OVERLAP
    top = 0
    while top < height and len(chunks) < MAX_CHUNKS:
        bottom = min(top + MAX_CHUNK_HEIGHT, height)
        chunks.append(image.crop((0, top, width, bottom)))
        if bottom == height:
            break
        top += step
    return chunks


def _image_to_base64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ──────────────────────────────────────────────────────
# LLM 호출 헬퍼
# ──────────────────────────────────────────────────────

def _validate_multivector(result: dict, group: str) -> list[str]:
    """멀티벡터 LLM 응답이 그룹별 필드 카운트 조건을 충족하는지 검증한다."""
    errors: list[str] = []
    required = GROUP_REQUIRED_COUNTS.get(group, {})
    for field, expected_count in required.items():
        value = result.get(field)
        if not isinstance(value, list):
            errors.append(f"[{field}] 리스트가 아님: {type(value)}")
            continue
        if len(value) != expected_count:
            errors.append(f"[{field}] 개수 불일치 — 기대 {expected_count}개, 실제 {len(value)}개")
        for i, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"[{field}][{i}] 빈 문자열 또는 비문자열")
    return errors


def _parse_llm_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


async def _extract_text_from_chunks(
    chunks: list[Image.Image], llm, product_name: str | None = None
) -> str:
    """이미지 청크 전체에서 상품 정보 텍스트를 추출한다."""
    image_content = []
    for chunk in chunks:
        b64 = _image_to_base64(chunk)
        image_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    name_hint = f"상품명: {product_name}\n\n" if product_name else ""
    image_content.append({
        "type": "text",
        "text": (
            f"{name_hint}"
            "위 이미지는 뷰티 상품의 상세페이지입니다.\n"
            "이미지에 표시된 모든 텍스트와 정보를 빠짐없이 추출하여\n"
            "상품명, 효능/기능, 성분, 사용법, 주의사항, 인증 정보, 수치 데이터 등을\n"
            "구조 없이 자연어로 서술해 주세요.\n"
            "이미지에 없는 내용은 추측하지 마세요."
        ),
    })

    response = await llm.ainvoke([HumanMessage(content=image_content)])
    return response.content


async def _extract_and_classify_from_chunks(
    chunks: list[Image.Image],
    llm,
    product_name: str,
    valid_categories: dict,
) -> dict:
    """이미지에서 텍스트 추출과 카테고리 분류를 한 번의 Vision LLM 호출로 수행한다."""
    image_content = []
    for chunk in chunks:
        b64 = _image_to_base64(chunk)
        image_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    categories_str = "\n".join(
        f"  {main_cat}: {', '.join(tags.keys())}"
        for main_cat, tags in valid_categories.items()
    )

    image_content.append({
        "type": "text",
        "text": (
            f"상품명: {product_name}\n\n"
            "위 이미지는 뷰티 상품의 상세페이지입니다. 다음 두 가지를 함께 수행해 주세요.\n\n"
            "1. 이미지에 표시된 모든 텍스트와 정보를 빠짐없이 추출하세요.\n"
            "   (상품명, 효능/기능, 성분, 사용법, 주의사항, 인증 정보, 수치 데이터 등, 구조 없이 자연어로)\n"
            "   이미지에 없는 내용은 추측하지 마세요.\n\n"
            "2. 이미지와 상품명을 바탕으로 아래 목록 중 가장 적합한 카테고리와 태그로 분류하세요.\n"
            "   반드시 목록에 있는 값만 사용하고, 적합한 항목이 없으면 null을 사용하세요.\n\n"
            f"유효한 카테고리와 태그 목록:\n{categories_str}\n\n"
            "JSON 형식으로만 응답하세요:\n"
            '{"extracted_text": "추출한 상품 정보 전문", '
            '"main_category": "메인카테고리명 또는 null", '
            '"tag": "태그명 또는 null", '
            '"confidence": "high|medium|low|none", '
            '"reason": "분류 근거 한 문장"}'
        ),
    })

    response = await llm.ainvoke([HumanMessage(content=image_content)])
    return _parse_llm_json(response.content)


# ──────────────────────────────────────────────────────
# 메인 서비스
# ──────────────────────────────────────────────────────

class ProductRegistrationService:
    """
    상품 상세 이미지 URL 목록과 카테고리 정보를 받아
    구조화된 상품 문서(JSON)를 생성한다.
    """

    def __init__(self, vision_model: str | None = None, document_model: str | None = None):
        model = Settings.chatgpt_model_name
        self._vision_llm   = get_llm(vision_model or model,   temperature=0)
        self._document_llm = get_llm(document_model or model, temperature=0.7)

    async def create_product_document(
        self,
        image_urls: Union[str, list[str]],
        main_category: str,
        tag: str,
        sub_tag: str = "",
        include_multivector: bool = False,
    ) -> dict:
        """
        Args:
            image_urls:          상품 상세 이미지 URL (단일 str 또는 list[str])
            main_category:       최상위 카테고리 — category.json 키 기준 (예: "스킨케어", "생활도구")
            tag:                 중분류 태그 (예: "클렌징", "용기&수저")
            sub_tag:             세부 서브태그 — 향수/바디 엣지 케이스에 사용 (예: "입욕제/배쓰밤")
            include_multivector: True이면 "multivector" 키에 멀티벡터 문서를 포함해서 반환

        Returns:
            include_multivector=False: 구조화된 상품 문서 dict
            include_multivector=True:  {"structured": {...}, "multivector": {...}}
        """
        if isinstance(image_urls, str):
            image_urls = [image_urls]

        if not is_valid_category_tag(main_category, tag):
            raise ValueError(
                f"유효하지 않은 조합: main_category={main_category!r}, tag={tag!r}"
            )

        extra_category = resolve_extra_category(main_category, tag)

        # tag 하위 sub_tags를 category_list로 자동 구성
        cat_data = _load_category_json()["categories"].get(main_category, {})
        category_list = cat_data.get(tag, [])

        # 1. 이미지 다운로드 → 청크 분할
        all_chunks = await self._prepare_chunks(image_urls)

        # 2. 이미지에서 상품 텍스트 추출
        product_document = await _extract_text_from_chunks(all_chunks, self._vision_llm)

        # 3. 카테고리에 맞는 프롬프트로 구조화 JSON 생성
        structured = await self._build_structured_document(
            product_document, main_category, extra_category, category_list
        )

        if not include_multivector:
            return structured

        multivector = await self.generate_multivector_document(
            structured, main_category, tag, sub_tag
        )
        return {"structured": structured, "multivector": multivector}

    # 내부 메서드

    async def _prepare_chunks(self, image_urls: list[str]) -> list[Image.Image]:
        images = await asyncio.gather(*[_download_image(url) for url in image_urls])
        chunks: list[Image.Image] = []
        for img in images:
            chunks.extend(_split_image(img))
        return chunks

    async def create_product_document_auto(
        self,
        image_urls: Union[str, list[str]],
        product_name: str,
        include_multivector: bool = False,
    ) -> dict:
        """
        이미지 URL과 상품명만으로 카테고리를 자동 추론하여 상품 문서를 생성한다.

        Args:
            image_urls:          상품 상세 이미지 URL (단일 str 또는 list[str])
            product_name:        상품명
            include_multivector: True이면 결과에 "multivector" 키를 포함해서 반환

        Returns:
            분류 성공 시: {"classified": True, "main_category": ..., "tag": ...,
                          "structured": {...} [, "multivector": {...}]}
            분류 실패 시: {"classified": False, "product_name": ..., "inferred_category": ...,
                          "inferred_tag": ..., "confidence": ..., "reason": ..., "extracted_text": ...}
        """
        if isinstance(image_urls, str):
            image_urls = [image_urls]

        # 1. 이미지 다운로드 → 청크 분할 → 텍스트 추출 + 카테고리 분류 (Vision LLM 1회)
        all_chunks = await self._prepare_chunks(image_urls)
        valid_categories = _load_category_json().get("categories", {})
        inferred = await _extract_and_classify_from_chunks(
            all_chunks, self._vision_llm, product_name, valid_categories
        )
        extracted_text = inferred.get("extracted_text", "")
        inferred_cat = inferred.get("main_category")
        inferred_tag = inferred.get("tag")

        main_category = inferred_cat

        # 2. 유효성 검사 — 유효하지 않으면 분류 불가 결과 반환
        if not main_category or not inferred_tag or not is_valid_category_tag(main_category, inferred_tag):
            return {
                "classified": False,
                "product_name": product_name,
                "inferred_category": inferred_cat,
                "inferred_tag": inferred_tag,
                "confidence": inferred.get("confidence"),
                "reason": inferred.get("reason"),
                "extracted_text": extracted_text,
            }

        # 3. 해당 카테고리의 sub_tags를 category_list로 자동 구성
        cat_data = _load_category_json()["categories"].get(main_category, {})
        category_list = [sub for subs in cat_data.values() for sub in subs]

        # 4. 구조화 문서 생성
        extra_category = resolve_extra_category(main_category, inferred_tag)
        structured = await self._build_structured_document(
            extracted_text, main_category, extra_category, category_list
        )
        result = {
            "classified": True,
            "main_category": main_category,
            "tag": inferred_tag,
            "confidence": inferred.get("confidence"),
            "structured": structured,
        }
        if include_multivector:
            result["multivector"] = await self.generate_multivector_document(
                structured, main_category, inferred_tag
            )
        return result

    async def _build_structured_document(
        self,
        product_document: str,
        main_category: str,
        extra_category: str,
        category_list: list[str],
    ) -> dict:
        builder = _PROMPT_BUILDERS.get(main_category)
        if builder is None:
            raise ValueError(
                f"지원하지 않는 카테고리: '{main_category}'. "
                f"지원 목록: {list(_PROMPT_BUILDERS.keys())}"
            )

        prompt = builder(extra_category, product_document, category_list)
        response = await self._document_llm.ainvoke([HumanMessage(content=prompt)])
        return _parse_llm_json(response.content)

    async def generate_multivector_document(
        self,
        structured: dict,
        main_category: str,
        tag: str,
        sub_tag: str = "",
    ) -> dict:
        """
        구조화된 상품 정보를 멀티벡터 검색용 문서로 변환한다.

        Args:
            structured:    create_product_document()가 반환한 구조화 dict
            main_category: 최상위 카테고리 (예: "스킨케어")
            tag:           중분류 태그     (예: "클렌징")
            sub_tag:       세부 서브태그   (예: "입욕제/배쓰밤") — 향수/바디 분기에 사용

        Returns:
            {
              "combined": [...],
              "function_desc": [...],
              "attribute_desc": [...],
              "target_user": [...],
              "spec_feature": [...],
              "_group": "A"|"B"|...|"G"
            }

        Raises:
            ValueError: 검증 실패가 재시도 후에도 해소되지 않는 경우
        """
        prompt, group = build_multivector_prompt(structured, main_category, tag, sub_tag)

        for attempt in range(2):
            response = await self._document_llm.ainvoke([HumanMessage(content=prompt)])
            result = _parse_llm_json(response.content)
            errors = _validate_multivector(result, group)
            if not errors:
                result["_group"] = group
                return result
            if attempt == 0:
                continue  # 재시도

        raise ValueError(
            f"멀티벡터 문서 생성 실패 (그룹 {group}). 오류: {errors}"
        )

    async def register_product(self, record: dict) -> dict:
        """
        JSONL 레코드 1개를 받아 구조화 → 멀티벡터 → DB 저장 → OpenSearch 색인을 수행한다.

        Args:
            record: JSONL 한 줄 dict.
                    필수 키: 브랜드, 상품명, 상품상세_이미지, main_category, tag
                    선택 키: sub_tag, url, 별점, 리뷰_갯수, 원가, 할인율, 판매가, 상품이미지

        Returns:
            성공: {"success": True, "product_id": ..., "product_name": ...}
            실패: {"success": False, "product_name": ..., "error": ...}
        """
        product_name = record.get("상품명", "")
        try:
            image_urls = record.get("상품상세_이미지", [])

            logger.info(
                "register_product_start",
                product_name=product_name,
                image_count=len(image_urls),
            )

            # 1. 카테고리 자동 분류 + 구조화 + 멀티벡터 생성
            result = await self.create_product_document_auto(
                image_urls=image_urls,
                product_name=product_name,
                include_multivector=True,
            )
            if not result.get("classified"):
                logger.warning(
                    "register_product_classify_failed",
                    product_name=product_name,
                    confidence=result.get("confidence"),
                    reason=result.get("reason"),
                )
                return {
                    "success": False,
                    "product_name": product_name,
                    "error": f"카테고리 분류 실패 (confidence={result.get('confidence')}, reason={result.get('reason')})",
                }
            main_category = result["main_category"]
            tag = result["tag"]
            structured = result["structured"]
            multivector = result["multivector"]
            group = multivector.pop("_group", "")

            logger.info(
                "register_product_classified",
                product_name=product_name,
                main_category=main_category,
                tag=tag,
                confidence=result.get("confidence"),
            )

            # 2. product_id 생성
            code = _CATEGORY_CODE.get(main_category, "X")
            product_id = f"{code}{datetime.now().strftime('%Y%m')}{uuid4().hex[:6].upper()}"

            # 3. products 테이블 payload 구성
            product_data: dict = {
                "product_id":        product_id,
                "product_name":      record["상품명"],
                "brand":             record["브랜드"],
                "category":          main_category,
                "tag":               tag,
                "review_count":      record.get("리뷰_갯수") or 0,
                "product_image_url": record.get("상품이미지") or [],
                "product_page_url":  record.get("url") or "",
            }
            # None이 아닌 경우만 포함 (DB 컬럼 기본값 유지)
            for key, jsonl_key in [
                ("rating", "별점"),
                ("original_price", "원가"),
                ("discount_rate", "할인율"),
                ("sale_price", "판매가"),
            ]:
                val = record.get(jsonl_key)
                if val is not None:
                    product_data[key] = val

            # structured["category"]는 LLM이 출력하는 sub_tag 값 (예: "클렌징폼")
            if "category" in structured:
                product_data["sub_tag"] = structured["category"]

            # structured → 테이블 컬럼 매핑 (TEXT[], INTEGER[] 등)
            for field in _STRUCTURED_TABLE_FIELDS:
                if field in structured:
                    product_data[field] = structured[field]

            # 테이블 컬럼에 없는 나머지 → product_details (JSONB)
            product_details = {k: v for k, v in structured.items() if k not in _ALL_TABLE_FIELDS}
            if product_details:
                product_data["product_details"] = product_details

            # 4. OpenSearch 먼저 색인 → vectordb_id 수집
            logger.info(
                "register_product_opensearch_start",
                product_name=product_name,
                product_id=product_id,
                group=group,
            )
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{settings.opensearch_api_url}/api/product/index-multivector",
                    json={
                        "product_id": product_id,
                        "group":      group,
                        "multivector": multivector,
                    },
                )
                r.raise_for_status()
                product_data["vectordb_id"] = r.json().get("vectordb_id", {})
            logger.info("register_product_opensearch_done", product_name=product_name, product_id=product_id)

            # 5. DB 저장 (vectordb_id 포함)
            logger.info("register_product_db_start", product_name=product_name, product_id=product_id)
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{settings.database_api_url}/api/products",
                    json=product_data,
                )
                r.raise_for_status()

            logger.info(
                "register_product_success",
                product_name=product_name,
                product_id=product_id,
                main_category=main_category,
                tag=tag,
            )
            return {"success": True, "product_id": product_id, "product_name": product_name}

        except Exception as e:
            logger.error(
                "register_product_error",
                product_name=product_name,
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            return {"success": False, "product_name": product_name, "error": str(e)}


# ──────────────────────────────────────────────────────
# register_product 상수
# ──────────────────────────────────────────────────────

_CATEGORY_CODE: dict[str, str] = {
    "스킨케어": "S", "색조": "C", "헤어": "H", "향수/바디": "F",
    "이너뷰티": "I", "생활도구": "L", "뷰티툴": "B",
}

# structured dict에서 products 테이블 컬럼으로 직접 매핑되는 필드
_STRUCTURED_TABLE_FIELDS = {
    "sub_tag", "skin_type", "concerns", "preferred_colors",
    "preferred_ingredients", "avoided_ingredients", "preferred_scents",
    "lifestyle_values", "exclusive_product", "personal_color",
    "skin_shades", "product_comment",
}

# products 테이블의 모든 컬럼 (structured 나머지 → product_details 판단용)
_ALL_TABLE_FIELDS = _STRUCTURED_TABLE_FIELDS | {
    "product_id", "product_name", "brand", "category", "tag",
    "rating", "review_count", "original_price", "discount_rate", "sale_price",
    "product_image_url", "product_page_url",
    "vectordb_id", "product_details", "product_created_at",
}


# ──────────────────────────────────────────────────────
# 싱글턴
# ──────────────────────────────────────────────────────

_instance: ProductRegistrationService | None = None


def get_product_registration_service() -> ProductRegistrationService:
    global _instance
    if _instance is None:
        _instance = ProductRegistrationService()
    return _instance
