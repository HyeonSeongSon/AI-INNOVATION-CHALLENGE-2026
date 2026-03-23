from typing import Annotated, Dict, Any, List
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from ..base.base_state import BaseState


class MarketingAssistantState(BaseState):
    # -------------------------
    # 대화 메시지 (멀티턴)
    # -------------------------
    messages: Annotated[list[AnyMessage], add_messages]

    # -------------------------
    # 검색 / 추천
    # -------------------------
    search_queries: Dict[str, str]              # 페르소나 기반 검색 쿼리 (user_need_query, user_preference_query, retrieval, persona)
    recommended_products: List[Dict[str, Any]]  # 추천 상품 목록

    # -------------------------
    # CRM 메시지 생성
    # -------------------------
    generated_tasks: List[Dict[str, Any]]       # 생성된 CRM 메시지 및 품질 검사용 데이터 (product_id, brand, purpose, product_info, message)
