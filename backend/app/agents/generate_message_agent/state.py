from ..base.base_state import BaseState
from typing import Dict, List, Any, Optional

class GenerateMessageState(BaseState):
    generated_tasks: List[Dict[str, Any]]       # 생성된 CRM 메시지 및 품질 검사용 데이터 (product_id, brand, purpose, product_info, message)
    quality_failed_tasks: List[Dict[str, Any]]  # 품질 검사 최종 실패 태스크 (DB 저장용, 사용자 비노출)
    failed_task_ids: List[str]                  # 품질 검사 실패 태스크 ID 목록
    feedback_retry_count: int                   # 피드백 적용 재시도 횟수
    tasks: Optional[List[Dict[str, Any]]]       # 라우터가 추출한 생성 태스크 목록 (generate_message_node 입력)
    feedback_input: Optional[Dict[str, Any]]    # 라우터가 추출한 사용자 피드백 입력 (message_feedback_node 입력)
    persona_id: Optional[str]                   # 턴별 라우터 추출 페르소나 ID (매 턴 초기화)
    active_persona_id: Optional[str]            # 턴 간 유지되는 유효 페르소나 ID (router가 None 반환 시 fallback)