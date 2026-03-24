import json
from typing import Dict
from ..prompts.generate_persona_search_query_prompt import build_generate_product_search_query_from_persona_prompt

async def generate_product_search_query_from_persona(llm, persona_info) -> Dict:
    prompt = build_generate_product_search_query_from_persona_prompt(persona_info)
    response = await llm.ainvoke(prompt)
    return json.loads(response.content)