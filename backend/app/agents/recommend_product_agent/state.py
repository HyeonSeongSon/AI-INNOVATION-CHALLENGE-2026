from ..base.base_state import BaseState
from typing import Any, Dict, List, Optional

class RecommendProductState(BaseState):
    parsed_data: Dict[str, Any]
    search_queries: Dict[str, str]   # 페르소나 기반 검색 쿼리 (user_need_query, user_preference_query, retrieval, persona)
    recommended_products: List[Dict[str, Any]]
    active_persona_id: Optional[str]  # 턴 간 유지되는 현재 활성 페르소나 ID