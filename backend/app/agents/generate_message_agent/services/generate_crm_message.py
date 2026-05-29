import asyncio
from ....core.data_loader import get_brand_tone
from ....core.llm_utils import ainvoke_with_timeout
from ...shared.product.product_client import ProductClient
from ...shared.persona.persona_client import PersonaClient
from typing import Dict, List, Optional
from ..prompts.purpose_prompt import PurPosePrompts
from ....core.logging import get_logger

logger = get_logger(__name__)



class CrmMessageGenerator:
    def __init__(self):
        self._purpose = PurPosePrompts()
        self._product_client = ProductClient()
        self._persona_client = PersonaClient()
        self._purpose_prompt_map = {
            "브랜드/제품 첫소개": self._purpose.build_purpose_introduction_prompt,
            "신제품 홍보": self._purpose.build_purpose_new_products_prompt,
            "베스트셀러 제품 소개": self._purpose.build_purpose_bestseller_prompt,
            "프로모션/이벤트 소개": self._purpose.build_purpose_promotion_and_event_prompt,
            "성분/효능 강조 소개": self._purpose.build_purpose_ingredient_efficacy_point_prompt,
            "피부타입/고민 강조 소개": self._purpose.build_purpose_skintype_and_concern_point_prompt,
            "라이프스타일/연령대 강조 소개": self._purpose.build_purpose_lifestyle_and_age_point_prompt,
        }

    async def get_persona_info(self, persona_id: str) -> Optional[Dict]:
        """persona_id로 DB에서 페르소나 정보를 조회해 반환."""
        try:
            return await self._persona_client.get_persona_info(persona_id)
        except Exception as e:
            logger.error("persona_fetch_failed", persona_id=persona_id, error_type=type(e).__name__, exc_info=True)
            raise

    async def _get_product_info(self, product_id: str) -> dict:
        """단일 상품 ID로 DB에서 상품 정보를 조회하고 flat dict로 반환.

        Args:
            product_id: 조회할 상품의 고유 ID.

        Returns:
            상품 정보를 담은 flat dict. 상품이 없으면 빈 dict.
        """
        db_products = await self._product_client.get_products_detail_from_db([product_id])
        db_product = db_products[0] if db_products else {}
        return self._product_client.flatten_product_data(db_product)

    async def get_product_info(self, tasks: List[Dict]) -> List[Dict]:
        """각 태스크의 product_id로 상품 정보를 병렬 조회하여 task에 추가.

        Args:
            tasks: product_id 키를 포함하는 태스크 dict 리스트.

        Returns:
            product_info가 추가된 태스크 리스트. 조회 실패한 항목은 제외.
        """
        logger.info("get_product_info.start", task_count=len(tasks))

        fetch_tasks = [self._get_product_info(item["product_id"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        enriched = []
        for item, product_info in zip(tasks, results):
            if isinstance(product_info, Exception):
                logger.warning("get_product_info.fetch_failed", product_id=item["product_id"], error_type=type(product_info).__name__)
                continue
            if product_info:
                enriched.append({**item, "product_info": product_info})

        logger.info("get_product_info.done", fetched_count=len(enriched))
        return enriched

    async def get_brand_tone(self, tasks: List[Dict]) -> List[Dict]:
        """각 태스크의 브랜드명으로 브랜드 톤을 조회하여 task에 추가.

        브랜드 톤을 찾지 못한 항목은 결과에서 제외되며 경고 로그가 남음.

        Args:
            tasks: product_info.brand 키를 포함하는 태스크 dict 리스트.

        Returns:
            brand_tone이 추가된 태스크 리스트. 톤을 찾지 못한 항목은 제외.
        """
        result = [
            {**item, "brand_tone": brand_tone}
            for item in tasks
            if (brand_tone := get_brand_tone(item["product_info"].get("brand", "")))
        ]

        skipped = len(tasks) - len(result)
        if skipped:
            logger.warning("get_brand_tone.skipped", skipped_count=skipped)

        logger.info("get_brand_tone.done", task_count=len(result))
        return result

    async def get_crm_prompt(self, tasks: List[Dict], persona_info: Optional[Dict] = None) -> List[Dict]:
        """각 태스크의 purpose에 맞는 CRM 프롬프트를 생성하여 task에 추가.

        purpose 값을 키로 _purpose_prompt_map에서 프롬프트 빌더를 찾아
        product_info와 brand_tone을 인자로 호출함.

        Args:
            tasks: purpose, product_info, brand_tone 키를 포함하는 태스크 dict 리스트.
            persona_info: DB에서 조회한 페르소나 정보. None이면 페르소나 섹션 미포함.

        Returns:
            prompt가 추가된 태스크 리스트.
        """
        logger.info("get_crm_prompt.start", task_count=len(tasks))

        return [
            {**item, "prompt": self._purpose_prompt_map[item["purpose"]](item["product_info"], item["brand_tone"], persona_info=persona_info)}
            for item in tasks
        ]

    async def generate_crm_message(self, tasks: List[Dict], llm) -> List[Dict]:
        """각 태스크의 프롬프트로 LLM을 병렬 호출하여 CRM 메시지를 생성.

        Args:
            tasks: prompt 키를 포함하는 태스크 dict 리스트.
            llm: ainvoke 메서드를 지원하는 LangChain LLM 인스턴스.

        Returns:
            message가 추가된 태스크 리스트. 생성 결과가 없는 항목은 제외.
        """
        logger.info("generate_crm_message.start", task_count=len(tasks))

        fetch_tasks = [ainvoke_with_timeout(llm, item["prompt"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        messages = [
            {**item, "message": message}
            for item, message in zip(tasks, results)
            if not isinstance(message, Exception) and message
        ]

        skipped = sum(1 for r in results if isinstance(r, Exception))
        if skipped:
            logger.warning("generate_crm_message.partial_failure", skipped_count=skipped)

        logger.info("generate_crm_message.done", generated_count=len(messages))
        return messages
