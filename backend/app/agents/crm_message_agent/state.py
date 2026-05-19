from typing import Any, Dict, List, Optional, Annotated
from ..base.base_state import BaseState


def _overwrite(current: list, new: list) -> list:
    """initial_state에서 []를 주입해 턴마다 리셋하는 reducer. (recommended_products, generated_tasks, task_plan에 적용)"""
    return new


class CRMMessageAgentState(BaseState):
    file_records: Optional[List[Dict[str, Any]]]
    recommended_products: Annotated[List[Dict[str, Any]], _overwrite]  # turn-scope
    generated_tasks: Annotated[List[Dict[str, Any]], _overwrite]        # turn-scope
    active_persona_id: Optional[str]                                    # conversation-scope
    task_plan: Annotated[List[str], _overwrite]                         # turn-scope: 첫 LLM 라우팅 결과 저장
    summary: str                                                         # conversation-scope: 오래된 메시지 LLM 요약본
