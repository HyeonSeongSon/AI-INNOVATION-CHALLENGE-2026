"""
CRM 메시지 생성 API 엔드포인트
Tool Calling 방식 에이전트 사용
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any

# Agent import (relative import)
from ..service.agent.message_agent.crm_agent_tool_calling import CRMMessageAgent

# 라우터 생성
router = APIRouter(prefix="/api/crm", tags=["CRM"])

# Agent 인스턴스 (싱글톤)
_agent_instance = None


def get_agent() -> CRMMessageAgent:
    """Agent 인스턴스 가져오기 (싱글톤)"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = CRMMessageAgent()
    return _agent_instance


# ============================================================
# 데이터 모델
# ============================================================

class CRMRequest(BaseModel):
    """CRM 메시지 생성 요청"""
    user_input: str  # JSON 또는 자연어
    thread_id: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "user_input": '{"persona_id": "PERSONA_002", "purpose": "신상품홍보", "product_categories": ["립스틱"]}'
            }
        }


class ProductSelection(BaseModel):
    """제품 선택 요청"""
    thread_id: str
    selected_product_id: str

    class Config:
        schema_extra = {
            "example": {
                "thread_id": "thread-abc123",
                "selected_product_id": "PROD001"
            }
        }


class CRMResponse(BaseModel):
    """CRM 메시지 생성 응답"""
    status: Literal["needs_selection", "completed", "error"]
    thread_id: str
    recommended_products: Optional[List[Dict[str, Any]]] = None
    persona_info: Optional[Dict[str, Any]] = None
    search_query: Optional[str] = None
    count: Optional[int] = None
    final_message: Optional[Any] = None
    selected_product: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/generate", response_model=CRMResponse)
async def generate_crm_message(request: CRMRequest):
    """
    1단계: CRM 메시지 생성 시작

    - LLM이 툴을 선택하여 실행
    - recommend_products 실행 후 Interrupt 발생
    - 추천 제품 목록 반환

    **흐름**:
    1. parse_crm_message_request 툴 호출 (LLM 자동 판단)
    2. recommend_products 툴 호출 (LLM 자동 판단)
    3. Interrupt 발생 → 제품 목록 반환
    """
    try:
        agent = get_agent()

        result = agent.generate(
            user_input=request.user_input,
            thread_id=request.thread_id
        )

        return CRMResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/select-product", response_model=CRMResponse)
async def select_product(request: ProductSelection):
    """
    2단계: 사용자 제품 선택 처리

    - 선택한 제품 정보를 메시지로 추가
    - Agent 재개 → create_product_message 실행
    - 최종 CRM 메시지 생성 완료

    **흐름**:
    1. 사용자 선택을 HumanMessage로 추가
    2. Agent 재개
    3. create_product_message 툴 호출 (LLM 자동 판단)
    4. 최종 메시지 반환
    """
    try:
        agent = get_agent()

        result = agent.select_product(
            thread_id=request.thread_id,
            selected_product_id=request.selected_product_id
        )

        return CRMResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "ok", "message": "CRM API is running"}
