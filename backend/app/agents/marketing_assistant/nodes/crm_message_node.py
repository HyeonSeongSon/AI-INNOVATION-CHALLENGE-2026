import json
import re
from ..state import MarketingAssistantState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from ....core.llm_factory import get_llm
from ....config.settings import settings


def _parse_message(ai_message) -> dict:
    """AIMessage content에서 JSON 파싱 → {title, message}"""
    content = ai_message.content if hasattr(ai_message, "content") else str(ai_message)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        content = match.group(1)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"title": "", "message": content}


async def crm_message_node(state: MarketingAssistantState, config: RunnableConfig):
    services = config["configurable"]["services"]
    parser = services.parser
    generator = services.crm_generator

    message = state.get("messages", [])
    model_name = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    parser_llm = get_llm(settings.parser_model_name, temperature=0)
    message_llm = get_llm(model_name, temperature=0.7)

    tasks = await parser.crm_message_parser(message, parser_llm)
    tasks = await generator.get_product_info(tasks)
    tasks = await generator.get_brand_tone(tasks)
    tasks = await generator.get_crm_prompt(tasks)
    tasks = await generator.generate_crm_message(tasks, message_llm)

    # product_id, purpose, brand, message 저장 — product_info는 품질 평가 노드에서 재조회
    generated_tasks = [
        {
            "product_id": t["product_id"],
            "product_name": t.get("product_info", {}).get("product_name", ""),
            "brand": t.get("product_info", {}).get("brand", ""),
            "sub_tag": t.get("product_info", {}).get("sub_tag", ""),
            "purpose": t["purpose"],
            "message": _parse_message(t["message"]),
        }
        for t in tasks
    ]

    return Command(goto="quality_check_node", update={"generated_tasks": generated_tasks})
