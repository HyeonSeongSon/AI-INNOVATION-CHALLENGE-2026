from datetime import datetime, timezone
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from ...config.settings import settings
from ...core.llm_factory import get_llm
from ...core.logging import AgentLogger
from ..shared.parser_and_router.parser_and_router_request import recommend_product_parser
from ..shared.persona.generate_persona_and_query import generate_search_query, generate_structured_persona_info
from .state import RecommendProductState
import asyncio


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_node(state: RecommendProductState) -> dict:
    logger = AgentLogger({**state, "logs": []}, node_name="init_node", agent_name="recommend_product_agent")
    logger.info("agent_started", user_message="[init] 에이전트 시작")
    return {
        "search_queries": {},
        "recommended_products": [],
        "status": "running",
        "error": None,
        "error_details": None,
        "logs": logger.get_user_logs(),
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
    logger = AgentLogger(state, node_name=node_name, agent_name="recommend_product_agent")
    logger.info("parser_started", user_message=f"[{node_name}] 요청 파싱 시작")
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

        parsed_data = await recommend_product_parser(messages, parser_llm)
        logger.info("parser_done", user_message=f"[{node_name}] 요청 파싱 완료")
        return {
            **base,
            "parsed_data": parsed_data,
            "intermediate": {**state.get("intermediate", {}), "parsed_data": parsed_data},
            "logs": logger.get_user_logs(),
        }
    except Exception as e:
        logger.error("parser_error", user_message=f"[{node_name}] 오류가 발생했습니다.", error_type=type(e).__name__, exc_info=True)
        return {
            **base,
            "status": "failed",
            "error": "요청 파싱 중 오류가 발생했습니다.",
            "error_details": {"node": node_name},
            "logs": logger.get_user_logs(),
        }


async def get_search_query_node(state: RecommendProductState, config: RunnableConfig) -> Dict[str, Any]:
    recommender = config["configurable"]["services"].recommender
    node_name = "get_search_query"
    logger = AgentLogger(state, node_name=node_name, agent_name="recommend_product_agent")
    logger.info("get_search_query_started", user_message=f"[{node_name}] 검색 쿼리 생성 시작")
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
        query_llm = get_llm(model, temperature=settings.llm_temperature_persona)

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
            user_id = config.get("configurable", {}).get("user_id")
            search_queries = await recommender.get_product_search_queries(resolved_persona_id, user_id=user_id)

            if search_queries is None:
                logger.warning(
                    "persona_not_found",
                    user_message=f"[{node_name}] 페르소나 검색 쿼리 없음 (persona_id={resolved_persona_id})",
                    persona_id=resolved_persona_id,
                )
                return {
                    **base,
                    "messages": [AIMessage(content="해당 페르소나에 대한 상품 검색 쿼리를 찾을 수 없습니다. 올바른 페르소나 id인지 확인해주세요.", name="recommend_product_agent")],
                    "search_queries": {},
                    "status": "completed",
                    "decisions": {**state.get("decisions", {}), "search_query_source": source, "persona_found": False},
                    "logs": logger.get_user_logs(),
                }
        else:
            structured_persona, raw_queries = await asyncio.gather(
                generate_structured_persona_info(messages[-1:], query_llm),
                generate_search_query(messages[-1:], query_llm)
            )

            user_id = config.get("configurable", {}).get("user_id")
            resolved_persona_id = await recommender.persona_client.save_persona(structured_persona, user_id=user_id)
            await recommender.persona_client.save_product_search_query(resolved_persona_id, raw_queries, user_id=user_id)

            search_queries = {
                "user_need_query": raw_queries["need"],
                "user_preference_query": raw_queries["preference"],
                "retrieval": raw_queries["retrieval"],
                "persona": raw_queries["persona"],
            }

        logger.info(
            "get_search_query_done",
            user_message=f"[{node_name}] 검색 쿼리 준비 완료 (source={source}, persona_id={resolved_persona_id})",
            source=source,
            persona_id=resolved_persona_id,
        )
        return {
            **base,
            "search_queries": search_queries,
            "active_persona_id": resolved_persona_id,
            "decisions": {**state.get("decisions", {}), "search_query_source": source},
            "intermediate": {**state.get("intermediate", {}), "search_queries": search_queries},
            "logs": logger.get_user_logs(),
        }
    except Exception as e:
        logger.error("get_search_query_error", user_message=f"[{node_name}] 오류가 발생했습니다.", error_type=type(e).__name__, exc_info=True)
        return {
            **base,
            "status": "failed",
            "error": "검색 쿼리 생성 중 오류가 발생했습니다.",
            "error_details": {"node": node_name},
            "logs": logger.get_user_logs(),
        }


async def recommend_products_node(state: RecommendProductState, config: RunnableConfig) -> Dict[str, Any]:
    recommender = config["configurable"]["services"].recommender
    node_name = "recommend_products"
    logger = AgentLogger(state, node_name=node_name, agent_name="recommend_product_agent")
    logger.info("recommend_products_started", user_message=f"[{node_name}] 상품 추천 시작")
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

        retrieval_product_ids = await recommender.product_retriever(
            retrieval_query=search_queries["retrieval"],
            brands=parsed_data.get("brands") or None,
            sub_tags=parsed_data.get("product_categories") or None
        )

        recommended_products = await recommender.recommend(
            search_queries,
            retrieval_product_ids,
            product_tags=parsed_data.get("product_categories") or None,
        )
        recommended_products = [
            {k: v for k, v in p.items() if not k.endswith("_vector")}
            for p in recommended_products
        ]

        if not recommended_products:
            logger.info(
                "recommend_products_empty",
                user_message=f"[{node_name}] 조건에 맞는 추천 상품이 없습니다.",
            )
            return {
                **base,
                "messages": [AIMessage(content="조건에 맞는 추천 상품을 찾지 못했습니다.", name="recommend_product_agent")],
                "recommended_products": [],
                "status": "completed",
                "end_time": _now_iso(),
                "duration_ms": None,
                "intermediate": {**state.get("intermediate", {}), "recommended_products": []},
                "logs": logger.get_user_logs(),
            }

        product_summary = "\n".join(
            f"- [TOP{i+1}] [상품ID: {p.get('product_id')}] [{p.get('brand')}] {p.get('product_name')} ({p.get('sub_tag')}): {p.get('product_comment')}"
            for i, p in enumerate(recommended_products)
        )

        end_time = _now_iso()
        start_time = state.get("start_time")
        duration_ms = None
        if start_time:
            duration_ms = (datetime.fromisoformat(end_time) - datetime.fromisoformat(start_time)).total_seconds() * 1000

        logger.info(
            "recommend_products_done",
            user_message=f"[{node_name}] 상품 추천 완료 ({len(recommended_products)}개, {duration_ms:.0f}ms)",
            product_count=len(recommended_products),
            duration_ms=duration_ms,
        )
        return {
            **base,
            "messages": [AIMessage(content=f"추천 상품 목록 (스코어 순위 기준):\n{product_summary}", name="recommend_product_agent")],
            "recommended_products": recommended_products,
            "status": "completed",
            "end_time": end_time,
            "duration_ms": duration_ms,
            "intermediate": {**state.get("intermediate", {}), "recommended_products": recommended_products},
            "logs": logger.get_user_logs(),
        }
    except Exception as e:
        logger.error("recommend_products_error", user_message=f"[{node_name}] 오류가 발생했습니다.", error_type=type(e).__name__, exc_info=True)
        return {
            **base,
            "status": "failed",
            "error": "상품 추천 중 오류가 발생했습니다.",
            "error_details": {"node": node_name},
            "logs": logger.get_user_logs(),
        }
