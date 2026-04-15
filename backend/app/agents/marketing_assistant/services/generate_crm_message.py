import asyncio
from ....core.data_loader import get_brand_tones
from .product_client import ProductClient
from typing import Dict, List
from ..prompts.purpose_prompt import PurPosePrompts
from ....core.logging import get_logger

logger = get_logger(__name__)



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
        db_products = await self._product_client.get_products_detail_from_db([product_id])
        db_product = db_products[0] if db_products else {}
        return self._product_client.flatten_product_data(db_product)

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
