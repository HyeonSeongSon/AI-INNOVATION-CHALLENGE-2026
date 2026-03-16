import json
from typing import Dict
from ..prompts.generate_persona_search_query_prompt import build_generate_product_search_query_from_persona_prompt

async def generate_product_search_query_from_persona(llm, persona_info) -> Dict:
    prompt = build_generate_product_search_query_from_persona_prompt(persona_info)
    response = await llm.ainvoke(prompt)
    return json.loads(response.content)

if __name__ == "__main__":
    import asyncio
    import os
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
    from ....core.llm_factory import get_llm
    
    llm = get_llm(model_name="gpt-5-mini", temperature=0.7)

    persona_info = f"""김혜지님(21세, 학생)은 건성·민감 피부에 홍조가 있어 진정과 보습을 최우선으로 하되 7스킨/레이어링 루틴을 선호해 물토너·산뜻한 제형의 고수분 제품이 잘 맞습니다.
    퍼스널 컬러는 웜톤(쉐이드 19)이며 레드 계열을 선호하므로 따뜻한 레드·코랄 톤의 메이크업 컬러가 어울립니다. 
    나이아신아마이드를 선호하고 파라벤을 기피하며 친환경 가치를 중시하므로 성분 투명성·무파라벤, 크루얼티프리·펫세이프 요소를 가진 제품이 적합합니다. 
    시트러스 향을 좋아하지만 민감성 피부인 점을 고려해 저자극·약한 향의 시트러스 계열을 추천하며, 구매는 성분·안전성, 후기·랭킹, 효능을 중심으로 합리적으로 결정합니다"""

    response = asyncio.run(generate_product_search_query_from_persona(llm, persona_info))

    print(response)