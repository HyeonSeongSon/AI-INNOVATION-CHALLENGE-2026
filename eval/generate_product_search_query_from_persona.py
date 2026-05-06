import json
from typing import Dict

from ..prompts.classify_product_type_prompt import build_classify_product_type_prompt

from ..prompts.generate_beauty_tool_search_query_prompt import (
    build_generate_beauty_tool_search_query_from_persona_prompt,
)

from ..prompts.generate_user_vocab_search_query_prompt import (
    build_generate_user_vocab_product_search_query_from_persona_prompt,
)


async def generate_product_search_query_from_persona(llm, persona_info) -> Dict:
    # Stage 1: 품목 분류 + 핵심 신호 추출
    classify_prompt = build_classify_product_type_prompt(persona_info)
    classify_response = await llm.ainvoke(classify_prompt)
    classify_result = json.loads(classify_response.content)
    product_type = classify_result["product_type"]
    end_user = classify_result.get("end_user")
    product_form = classify_result.get("product_form")

    # Stage 2: 쿼리 생성
    query_prompt = build_generate_user_vocab_product_search_query_from_persona_prompt(
        persona_info, product_type, end_user=end_user, product_form=product_form
    )
    query_response = await llm.ainvoke(query_prompt)
    result = json.loads(query_response.content)
    result["_product_type"] = product_type  # 디버깅용 (선택적 제거 가능)
    result["_end_user"] = end_user          # 디버깅용
    result["_product_form"] = product_form  # 디버깅용
    return result
