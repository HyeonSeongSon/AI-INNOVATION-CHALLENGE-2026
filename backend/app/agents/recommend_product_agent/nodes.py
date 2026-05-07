import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from ...config.settings import settings
from ...core.llm_factory import get_llm
from ..shared.parser_and_router.parser_and_router_request import recommend_product_parser
from ..shared.persona.generate_persona_and_query import generate_search_query, generate_structured_persona_info
from .services.recommend_product_in_persona import ProductRecommender
from .state import RecommendProductState
import asyncio


_recommender = ProductRecommender()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_node(state: RecommendProductState) -> dict:
    return {
        "search_queries": {},
        "recommended_products": [],
        "status": "running",
        "error": None,
        "error_details": None,
        "logs": ["[init] 에이전트 시작"],
        "step": 0,
        "node_history": ["init"],
        "current_node": "init",
        "last_node": None,
        "is_interrupted": False,
        "start_time": _now_iso(),
        "end_time": None,
        "duration_ms": None,
        "intermediate": {},
        "decisions": {},
    }


async def parser_node(state: RecommendProductState, config: RunnableConfig) -> Dict[str, Any]:
    node_name = "parser"
    step = state.get("step", 0) + 1
    base = {
        "step": step,
        "current_node": node_name,
        "last_node": state.get("current_node"),
        "node_history": state.get("node_history", []) + [node_name],
    }
    try:
        messages = state["messages"]
        model = config.get("configurable", {}).get("model", settings.parser_model_name)
        parser_llm = get_llm(model, settings.parser_model_temperature)

        parsed_data = await recommend_product_parser(messages[-1:], parser_llm)
        return {
            **base,
            "parsed_data": parsed_data,
            "intermediate": {**state.get("intermediate", {}), "parsed_data": parsed_data},
            "logs": state.get("logs", []) + [f"[{node_name}] 요청 파싱 완료"],
        }
    except Exception as e:
        return {
            **base,
            "status": "failed",
            "error": str(e),
            "error_details": {"node": node_name, "traceback": traceback.format_exc()},
            "logs": state.get("logs", []) + [f"[{node_name}] 오류: {e}"],
        }


async def get_search_query_node(state: RecommendProductState, config: RunnableConfig) -> Dict[str, Any]:
    node_name = "get_search_query"
    step = state.get("step", 0) + 1
    base = {
        "step": step,
        "current_node": node_name,
        "last_node": state.get("current_node"),
        "node_history": state.get("node_history", []) + [node_name],
    }
    try:
        messages = state.get("messages")
        parsed_data = state.get("parsed_data")
        model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
        query_llm = get_llm(model, temperature=0.3)

        persona_id = parsed_data.get("persona_id")
        has_persona_info = parsed_data.get("has_persona_info", True)
        active_persona_id = state.get("active_persona_id")

        if persona_id:
            resolved_persona_id = persona_id
            source = "persona_id"
        elif not has_persona_info and active_persona_id:
            resolved_persona_id = active_persona_id
            source = "continuation"
        else:
            resolved_persona_id = None
            source = "generated"

        if resolved_persona_id:
            search_queries = await _recommender.get_product_search_queries(resolved_persona_id)

            if search_queries is None:
                return {
                    **base,
                    "messages": [AIMessage(content="해당 페르소나에 대한 상품 검색 쿼리를 찾을 수 없습니다. 올바른 페르소나 id인지 확인해주세요.")],
                    "search_queries": {},
                    "status": "completed",
                    "decisions": {**state.get("decisions", {}), "search_query_source": source, "persona_found": False},
                    "logs": state.get("logs", []) + [f"[{node_name}] 페르소나 검색 쿼리 없음 (persona_id={resolved_persona_id})"],
                }
        else:
            structured_persona, raw_queries = await asyncio.gather(
                generate_structured_persona_info(messages[-1:], query_llm),
                generate_search_query(messages[-1:], query_llm)
            )

            resolved_persona_id = await _recommender.persona_client.save_persona(structured_persona)
            await _recommender.persona_client.save_product_search_query(resolved_persona_id, raw_queries)

            search_queries = {
                "user_need_query": raw_queries["need"],
                "user_preference_query": raw_queries["preference"],
                "retrieval": raw_queries["retrieval"],
                "persona": raw_queries["persona"],
            }

        return {
            **base,
            "search_queries": search_queries,
            "active_persona_id": resolved_persona_id,
            "decisions": {**state.get("decisions", {}), "search_query_source": source},
            "intermediate": {**state.get("intermediate", {}), "search_queries": search_queries},
            "logs": state.get("logs", []) + [f"[{node_name}] 검색 쿼리 준비 완료 (source={source}, persona_id={resolved_persona_id})"],
        }
    except Exception as e:
        return {
            **base,
            "status": "failed",
            "error": str(e),
            "error_details": {"node": node_name, "traceback": traceback.format_exc()},
            "logs": state.get("logs", []) + [f"[{node_name}] 오류: {e}"],
        }


async def recommend_products_node(state: RecommendProductState) -> Dict[str, Any]:
    node_name = "recommend_products"
    step = state.get("step", 0) + 1
    base = {
        "step": step,
        "current_node": node_name,
        "last_node": state.get("current_node"),
        "node_history": state.get("node_history", []) + [node_name],
    }
    try:
        parsed_data = state.get("parsed_data")
        search_queries = state.get("search_queries")

        retrieval_product_ids = await _recommender.product_retriever(
            retrieval_query=search_queries["retrieval"],
            brands=parsed_data.get("brands") or None,
            sub_tags=parsed_data.get("product_categories") or None
        )

        recommended_products = await _recommender.recommend(
            search_queries,
            retrieval_product_ids,
            product_tags=parsed_data.get("product_categories") or None,
        )
        recommended_products = [
            {k: v for k, v in p.items() if not k.endswith("_vector")}
            for p in recommended_products
        ]

        product_summary = "\n".join(
            f"- [상품ID: {p.get('product_id')}] [{p.get('brand')}] {p.get('product_name')} ({p.get('sub_tag')}): {p.get('product_comment')}"
            for p in recommended_products
        )

        end_time = _now_iso()
        start_time = state.get("start_time")
        duration_ms = None
        if start_time:
            duration_ms = (datetime.fromisoformat(end_time) - datetime.fromisoformat(start_time)).total_seconds() * 1000

        return {
            **base,
            "messages": [AIMessage(content=f"추천 상품 목록:\n{product_summary}")],
            "recommended_products": recommended_products,
            "status": "completed",
            "end_time": end_time,
            "duration_ms": duration_ms,
            "intermediate": {**state.get("intermediate", {}), "recommended_products": recommended_products},
            "logs": state.get("logs", []) + [f"[{node_name}] 상품 추천 완료 ({len(recommended_products)}개, {duration_ms:.0f}ms)"],
        }
    except Exception as e:
        return {
            **base,
            "status": "failed",
            "error": str(e),
            "error_details": {"node": node_name, "traceback": traceback.format_exc()},
            "logs": state.get("logs", []) + [f"[{node_name}] 오류: {e}"],
        }
