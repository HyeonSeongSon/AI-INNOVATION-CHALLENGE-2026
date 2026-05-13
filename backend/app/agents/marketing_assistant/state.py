from typing import Dict, Any, List, Optional
from ..base.base_state import BaseState


class MarketingAssistantState(BaseState):
    search_queries: Dict[str, str]              # 페르소나 기반 검색 쿼리 (user_need_query, user_preference_query, retrieval, persona)
    recommended_products: List[Dict[str, Any]]  # 추천 상품 목록
    generated_tasks: List[Dict[str, Any]]       # 생성된 CRM 메시지 및 품질 검사용 데이터 (product_id, brand, purpose, product_info, message)
    failed_task_ids: List[str]                  # 품질 검사 실패 태스크 ID 목록
    feedback_retry_count: int                   # 피드백 적용 재시도 횟수
    file_records: Optional[List[Dict[str, Any]]]  # 업로드된 파일의 레코드 목록 (처리 후 None으로 초기화)
    product_registration_results: Optional[Dict[str, Any]]     # 등록 결과 요약
