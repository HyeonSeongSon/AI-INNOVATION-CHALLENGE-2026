from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from ..prompts.crm_parse_prompt import build_crm_parse_prompt
from ....core.logging import get_logger
from dotenv import load_dotenv
import os
import json

logger = get_logger("parse_crm_request")

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

# 카테고리 목록 로드
def load_categories():
    """categories.json에서 카테고리 목록 로드"""
    # 프로젝트 루트 찾기: /app 또는 로컬 개발 환경
    current_dir = os.path.dirname(__file__)

    # Docker 환경: /app/data/categories.json
    docker_path = "/app/data/categories.json"
    # 로컬 환경: backend/app/agents/crm_agent/services -> ../../../../../data/categories.json
    local_path = os.path.join(current_dir, "../../../../../data/categories.json")

    # Docker 환경 우선 시도
    if os.path.exists(docker_path):
        categories_path = docker_path
    else:
        categories_path = local_path

    with open(categories_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['categories']

class MultiMessageRequest(BaseModel):
    """다중 값을 지원하는 CRM 메시지 요청"""

    persona_id: Optional[str] = Field(
        default=None,
        description="페르소나 ID (단일 값). 예: 'P123' 또는 '20대 여성'"
    )

    purpose: Optional[str] = Field(
        default=None,
        description="메시지 목적 (단일 값). 예: '프로모션', '재구매유도'"
    )

    product_categories: List[str] = Field(
        default_factory=list,
        description="상품 카테고리 리스트. 예: ['스킨케어', '메이크업', '헤어케어']"
    )

    brands: List[str] = Field(
        default_factory=list,
        description="브랜드 리스트. 예: ['라네즈', '설화수', '이니스프리']"
    )

    exclusive_target: Optional[str] = Field(
        default=None,
        description="특정 대상 전용 제품 (단일 값). 예: '남성', '반려동물', '베이비', '임산부' 등. 없으면 None"
    )

class MultiValueParser:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        chat_gpt_model_name = os.getenv("CHATGPT_MODEL_NAME")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY가 설정되지 않았습니다. "
                "backend/app/.env 파일에 OPENAI_API_KEY를 설정해주세요."
            )

        self.llm = ChatOpenAI(model=chat_gpt_model_name, temperature=0, request_timeout=30)
        self.parser = self.llm.with_structured_output(MultiMessageRequest)
        logger.info("parser_initialized", model=chat_gpt_model_name)

    async def parse(self, user_input: str) -> str:
        """자연어 → 다중 값 파싱"""

        messages = [
            SystemMessage(content=build_crm_parse_prompt(load_categories())),
            HumanMessage(content=user_input)
        ]
        try:
            response = await self.parser.ainvoke(messages)
            return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("llm_parse_failed", error=str(e), exc_info=True)
            return json.dumps({"error": f"파싱 중 오류 발생: {str(e)}"}, ensure_ascii=False)

if __name__ == "__main__":
    import asyncio

    async def main():
        parser = MultiValueParser()
        user_input = "PERSONA_002로 설화수에 크림 제품 중 하나를 신상품 홍보 목적으로 광고메세지를 생성해줘"
        result = await parser.parse(user_input=user_input)
        print(result)

    asyncio.run(main())