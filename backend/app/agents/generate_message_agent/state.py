from ..base.base_state import BaseState
from typing import Dict, List, Any

class GenerateMessageState(BaseState):
    generated_tasks: List[Dict[str, Any]]       # 생성된 CRM 메시지 및 품질 검사용 데이터 (product_id, brand, purpose, product_info, message)
    failed_task_ids: List[str]                  # 품질 검사 실패 태스크 ID 목록
    feedback_retry_count: int                   # 피드백 적용 재시도 횟수