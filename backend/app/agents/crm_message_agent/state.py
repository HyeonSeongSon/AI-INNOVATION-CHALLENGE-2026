from typing import Any, Dict, List, Optional, Annotated
from ..base.base_state import BaseState


def _overwrite(current: list, new: list) -> list:
    """
    항상 새 값으로 덮어쓴다. 
    initial_state에서 []를 주입하면 턴마다 리셋된다.
    """
    return new


class CRMMessageAgentState(BaseState):
    file_records: Optional[List[Dict[str, Any]]]
    recommended_products: Annotated[List[Dict[str, Any]], _overwrite]  # turn-scope
    generated_tasks: Annotated[List[Dict[str, Any]], _overwrite]        # turn-scope
    active_persona_id: Optional[str]                                    # conversation-scope
