import asyncio
from ....core.data_loader import get_brand_tones
from .product_client import ProductClient
from typing import Dict, List
from ..prompts.purpose_prompt import PurPosePrompts
from ....core.logging import get_logger

logger = get_logger(__name__)

# 벡터 DB에서 제거할 필드:
# - category/카테고리/태그: 정형 DB의 product_tag로 대체
# - 정형 DB 영어 필드와 중복되는 한국어 필드
_VECTOR_EXCLUDE_KEYS = {
    "category", "카테고리", "태그",
    "상품명", "브랜드",
    "피부타입", "기피성분", "선호성분", "선호향",
    "가치관", "고민키워드", "선호포인트색상", "전용제품",
}

# 정형 DB에서 제거할 필드 (내부용, CRM 메시지 불필요)
_DB_EXCLUDE_KEYS = {
    "vectordb_id",
    "product_created_at",
}


class CrmMessageGenerator:
    def __init__(self):
        self._purpose = PurPosePrompts()
        self._product_client = ProductClient()
        self._purpose_prompt_map = {
            "브랜드/제품 첫소개": self._purpose.build_purpose_introduction_prompt,
            "신제품 홍보": self._purpose.build_purpose_new_products_prompt,
            "베스트셀러 제품 소개": self._purpose.build_purpose_bestseller_prompt,
            "프로모션/이벤트 소개": self._purpose.build_purpose_promotion_and_evnet_prompt,
            "성분/효능 강조 소개": self._purpose.build_purpose_ingredient_efficacy_point_prompt,
            "피부타입/고민 강조 소개": self._purpose.build_purpose_skintype_and_concern_point_prompt,
            "라이프스타일/연령대 강조 소개": self._purpose.build_purpose_lifestyle_and_age_point_prompt,
        }

    def _get_brand_tone(self, brand_name: str) -> str:
        brand_tones = get_brand_tones().get('brand_ton_prompt', {})

        if brand_name in brand_tones:
            return brand_tones[brand_name]

        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

    async def _get_product_info(self, product_id: str) -> dict:
        product_info_by_db, product_info_by_vectordb = await asyncio.gather(
            self._product_client.get_products_detail_from_db([product_id]),
            self._product_client.get_products_by_ids([product_id]),
        )

        db_map = {p["product_id"]: p for p in product_info_by_db if "product_id" in p}
        vector_map = {p["product_id"]: p for p in product_info_by_vectordb if "product_id" in p}

        vector = vector_map.get(product_id, {})
        db = db_map.get(product_id, {})

        vector_clean = {
            k: v for k, v in vector.items()
            if not k.endswith("_vector") and k not in _VECTOR_EXCLUDE_KEYS
        }
        db_clean = {k: v for k, v in db.items() if k not in _DB_EXCLUDE_KEYS}

        # 정형 DB가 베이스, 벡터 DB가 우선 (같은 키면 벡터 DB 값 사용)
        return {**db_clean, **vector_clean}

    async def get_product_info(self, tasks: List[Dict]) -> List[Dict]:
        logger.info("get_product_info.start", task_count=len(tasks))

        fetch_tasks = [self._get_product_info(item["product_id"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks)

        enriched = [
            {**item, "product_info": product_info}
            for item, product_info in zip(tasks, results)
            if product_info
        ]

        logger.info("get_product_info.done", fetched_count=len(enriched))
        return enriched

    async def get_brand_tone(self, tasks: List[Dict]) -> List[Dict]:
        result = [
            {**item, "brand_tone": brand_tone}
            for item in tasks
            if (brand_tone := self._get_brand_tone(item["product_info"]["brand"]))
        ]

        skipped = len(tasks) - len(result)
        if skipped:
            logger.warning("get_brand_tone.skipped", skipped_count=skipped)

        logger.info("get_brand_tone.done", task_count=len(result))
        return result

    async def get_crm_prompt(self, tasks: List[Dict]) -> List[Dict]:
        logger.info("get_crm_prompt.start", task_count=len(tasks))

        return [
            {**item, "prompt": self._purpose_prompt_map[item["purpose"]](item["product_info"], item["brand_tone"])}
            for item in tasks
        ]

    async def generate_crm_message(self, tasks: List[Dict], llm) -> List[Dict]:
        logger.info("generate_crm_message.start", task_count=len(tasks))

        fetch_tasks = [llm.ainvoke(item["prompt"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks)

        messages = [
            {**item, "message": message}
            for item, message in zip(tasks, results)
            if message
        ]

        logger.info("generate_crm_message.done", generated_count=len(messages))
        return messages
