from typing import Any, Dict, List, Optional

from ..base.base_state import BaseState


class DataRegistrationState(BaseState, total=False):
    file_records: Optional[List[Dict[str, Any]]]
