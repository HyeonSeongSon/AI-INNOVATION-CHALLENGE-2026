from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from ..prompts.parse_prompt import build_crm_parse_prompt, build_crm_message_parse_prompt
from ....core.logging import get_logger
import os
import json

logger = get_logger("parse_crm_request")

# 카테고리 목록 로드
def load_categories():
    """categories.json에서 카테고리 목록 로드"""
    current_dir = os.path.dirname(__file__)
    docker_path = "/app/data/categories.json"
    local_path = os.path.join(current_dir, "../../../../../data/categories.json")

    categories_path = docker_path if os.path.exists(docker_path) else local_path

    with open(categories_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['category_type']

class RecommendProductRequest(BaseModel):
    """다중 값을 지원하는 상품 추천 메시지 요청"""

    persona_id: Optional[str] = Field(
        default=None,
        description="페르소나 ID (단일 값). 예: 'P123' 또는 '20대 여성'"
    )

    product_categories: List[str] = Field(
        default_factory=list,
        description="상품 카테고리 리스트. 예: ['스킨케어', '메이크업', '헤어케어']"
    )

    brands: List[str] = Field(
        default_factory=list,
        description="브랜드 리스트. 예: ['라네즈', '설화수', '이니스프리']"
    )

class CRMMessageTask(BaseModel):
    """단일 상품-목적 조합"""
    product_id: str = Field(description="상품 ID. 예: 'p001'")
    purpose: Optional[str] = Field(default=None, description="메시지 목적. 예: '프로모션', '재구매유도'")


class CRMMessageParseResult(BaseModel):
    """CRM 메시지 파싱 결과 — 여러 상품이 언급된 경우 각각 별도 task"""
    tasks: List[CRMMessageTask] = Field(default_factory=list)
    
class MultiValueParser:
    def __init__(self):
        logger.info("parser_initialized")

    async def recommend_product_parser(self, user_input: str, llm: BaseChatModel) -> str:
        """자연어 → 다중 값 파싱

        Args:
            user_input: 사용자 입력 (자연어 또는 JSON)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)
        """
        parser = llm.with_structured_output(RecommendProductRequest)
        messages = [
            SystemMessage(content=build_crm_parse_prompt(load_categories())),
            HumanMessage(content=user_input)
        ]
        try:
            response = await parser.ainvoke(messages)
            return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            return json.dumps({"error": f"파싱 중 오류 발생: {str(e)}"}, ensure_ascii=False)
        
    async def crm_message_parser(self, user_input: str, llm: BaseChatModel) -> List[Dict[str, Any]]:
        """자연어 → product_id/purpose 파싱. 여러 상품이 언급된 경우 parallel 플래그와 함께 반환.

        Args:
            user_input: 사용자 입력 (자연어 또는 JSON)
            llm: 노드에서 생성된 LLM 인스턴스 (BaseChatModel)

        Returns:
            JSON 문자열. 예:
            단일: {"parallel": false, "tasks": [{"product_id": "p001", "purpose": "프로모션"}]}
            복수: {"parallel": true,  "tasks": [{"product_id": "p001", ...}, {"product_id": "p002", ...}]}
        """
        parser = llm.with_structured_output(CRMMessageParseResult)
        messages = [
            SystemMessage(content=build_crm_message_parse_prompt()),
            HumanMessage(content=user_input)
        ]
        try:
            response = await parser.ainvoke(messages)
            return [t.model_dump() for t in response.tasks]
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            raise
        
if __name__ == "__main__":
    import asyncio
    from ....core.llm_factory import get_llm
    from ....config.settings import Settings
    llm = get_llm(model_name="gpt-5-nano", temperature=0.7)
    parser = MultiValueParser()
    settings = Settings()
    user_input = "A20251200289, A20251200418, A20251200288, A20251207488 상품으로 베스트셀러 홍보 메시지를 만들고, A20251707488 상품으로 신제품 홍보 메시지를 만들어줘"
    result = asyncio.run(parser.crm_message_parser(user_input, llm))
    print(result)