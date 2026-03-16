from typing import Dict, Any, List, Optional
from ....config.settings import Settings
from .generate_product_search_query_from_persona import generate_product_search_query_from_persona
from .persona_client import PersonaClient
from ....core.llm_factory import get_llm
from ....core.logging import get_logger
import json
import httpx

_persona_client = PersonaClient()
logger = get_logger(__name__)

class ProductRecommender:
    def __init__(self):
        self.vector_db_api_url = Settings.opensearch_api_url
        self.db_api_url = Settings.database_api_url
        self.llm = get_llm(Settings.chatgpt_model_name, temperature=0.7)
    
    async def get_product_search_queries(self, persona_id):
        logger.info("product_search_queries.start", persona_id=persona_id)
        
        # 기존 상품 검색 쿼리 조회
        existing_product_search_queries = await _persona_client.get_existing_product_search_query(persona_id)

        if existing_product_search_queries:
            # 기존 검색 쿼리 사용
            logger.info("product_search_queries.cache_hit", persona_id=persona_id)
            search_queries = {
                "user_need_query": existing_product_search_queries['need']['text'],
                "user_preference_query": existing_product_search_queries['preference']['text'],
                "retrieval": existing_product_search_queries['retrieval']['text'],
                "persona": existing_product_search_queries['persona']['text']
            }
        else:
            # 기존 검색 쿼리 없으면 상품 검색 쿼리 생성
            logger.info("product_search_queries.generating", persona_id=persona_id)
            persona_info = await _persona_client.get_persona_info(persona_id)
            search_queries = await generate_product_search_query_from_persona(self.llm, persona_info)

            # DB저장
            await _persona_client.save_product_search_query(persona_id, search_queries)
            logger.info("product_search_queries.saved", persona_id=persona_id)

        logger.info("product_search_queries.done", persona_id=persona_id, query_keys=list(search_queries.keys()))
        return search_queries
    
    

    
if __name__ == "__main__":
    import asyncio
    persona_id = "PERSONA_6E6354965AB9"
    pr = ProductRecommender()
    queries = asyncio.run(pr.get_product_search_queries(persona_id))
    print(queries)