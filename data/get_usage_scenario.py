from ..backend.app.core.llm_factory import get_llm
from ..backend.app.config.settings import settings
import json
import asyncio


def prompt(product_structured) -> str:
    return f"""
    다음 상품 정보를 보고 usage_scenario를 작성하세요.

    규칙:
    1. 실제 사용자가 일상에서 쓰는 표현으로 작성 (제품 광고 문구 금지)
    2. 반드시 포함: 사용 시점/상황, 사용자 유형, 기대 효과
    3. 다음 사용자 표현을 활용:
    - "화장한 위에", "덧발라", "뿌려서", "수시로" (메이크업 위 사용 가능 제품)
    - "외근 중에", "이동 중에", "바쁜 직장인" (휴대성 강조 제품)
    - "달아오를 때", "발개질 때" (홍조 제품)
    - "피부결이 정돈", "들뜸 없이" (텍스처 관련)
    - "오래 촉촉하게", "당기지 않게" (보습 지속)
    4. 100~150자 내외로 작성

    상품 정보:
    - usage_context: {product_structured["usage_context"]}
    - target_user: {product_structured["target_user"]}
    - function: {product_structured["function"]}
    - concern: {product_structured["concern"]}
    - finish_type: {product_structured["finish_type"]}
    """
if __name__=="__main__":
    llm = get_llm(model_name=settings.chatgpt_model_name, temperature=0.7)