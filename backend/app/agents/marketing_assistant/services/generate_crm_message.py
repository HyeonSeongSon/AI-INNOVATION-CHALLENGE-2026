import asyncio
import yaml
from pathlib import Path
from ....core.llm_factory import get_llm
from ....config.settings import settings
from .product_client import ProductClient
from typing import Dict, Any, List
from ..prompts.purpose_prompt import PurPosePrompts

_purpose = PurPosePrompts()
_product_client = ProductClient()

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

_PURPOSE_PROMPT_MAP = {
            "브랜드/제품 첫소개": _purpose.build_purpose_introduction_prompt,
            "신제품 홍보": _purpose.build_purpose_new_products_prompt,
            "베스트셀러 제품 소개": _purpose.build_purpose_bestseller_prompt,
            "프로모션/이벤트 소개": _purpose.build_purpose_promotion_and_evnet_prompt,
            "성분/효능 강조 소개": _purpose.build_purpose_ingredient_efficacy_point_prompt,
            "피부타입/고민 강조 소개": _purpose.build_purpose_skintype_and_concern_point_prompt,
            "라이프스타일/연령대 강조 소개": _purpose.build_purpose_lifestyle_and_age_point_prompt
        }


class CRMMessageGenerator:
    def __init__(self):
        self.parser_llm = get_llm(model_name=settings.parser_model_name, temperature=0)
        self.llm = get_llm(model_name=settings.chatgpt_model_name, temperature=0.7)
        self.vector_db_api_url = settings.opensearch_api_url
        self.db_api_url = settings.database_api_url
        _brand_tone_path = Path(__file__).parent.parent / "prompts" / "brand_tone.yaml"
        self.brand_tones = self._load_yaml(str(_brand_tone_path))

    def _load_yaml(self, file_path: str) -> Dict[str, Any]:
        """YAML 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data
        except Exception:
            return {}

    def _get_brand_tone(self, brand_name: str) -> str:
        """브랜드톤 가져오기"""
        brand_tones = self.brand_tones.get('brand_ton_prompt', {})

        # 정확한 브랜드명으로 검색
        if brand_name in brand_tones:
            return brand_tones[brand_name]

        # 대소문자 무시하고 검색
        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

    async def _get_product_info(self, product_id: str) -> dict:
        product_info_by_db, product_info_by_vectordb = await asyncio.gather(
            _product_client.get_products_detail_from_db([product_id]),
            _product_client.get_products_by_ids([product_id]),
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
        fetch_tasks = [self._get_product_info(item["product_id"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks)

        return [
            {**item, "product_info": product_info}
            for item, product_info in zip(tasks, results)
            if product_info
        ]

    async def get_brand_tone(self, tasks: List[Dict]) -> List[Dict]:
        return [
            {**item, "brand_tone": brand_tone}
            for item in tasks
            if (brand_tone := self._get_brand_tone(item["product_info"]["brand"]))
        ]

    async def get_crm_prompt(self, tasks: List[Dict]) -> List[Dict]:
        return [
            {**item, "prompt": _PURPOSE_PROMPT_MAP[item["purpose"]](item["product_info"], item["brand_tone"])}
            for item in tasks
        ]

    async def generate_crm_message(self, tasks: List[Dict], llm) -> List[Dict]:
        fetch_tasks = [llm.ainvoke(item["prompt"]) for item in tasks]
        results = await asyncio.gather(*fetch_tasks)

        return [
            {**item, "message": message}
            for item, message in zip(tasks, results)
            if message
        ]
        
if __name__=="__main__":
    cmg = CRMMessageGenerator()
    test_tasks = [
        {"product_id": "A20251200289", "purpose": "베스트셀러 제품 소개"},
        {"product_id": "A20251200230", "purpose": "신제품 홍보"},
    ]
    result = asyncio.run(cmg.get_product_info(test_tasks))
    print(result)