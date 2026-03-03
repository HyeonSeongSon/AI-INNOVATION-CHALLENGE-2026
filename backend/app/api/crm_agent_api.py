"""
CRM 메시지 생성 API 엔드포인트
Tool Calling 방식 에이전트 사용
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any

# Agent import (relative import)
from ..agents.crm_agent.crm_agent import CRMAgent

# Logging
from ..core.logging import get_logger
from ..core.context import set_agent_name

logger = get_logger("crm_api")

# 라우터 생성
router = APIRouter(prefix="/api/crm", tags=["CRM"])

# Agent 인스턴스 (싱글톤)
_agent_instance = None


def get_agent() -> CRMAgent:
    """Agent 인스턴스 가져오기 (싱글톤)"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = CRMAgent()
    return _agent_instance


# ============================================================
# 데이터 모델
# ============================================================

class CRMRequest(BaseModel):
    """CRM 메시지 생성 요청"""
    user_input: str                     # JSON 또는 자연어
    session_id: Optional[str] = None   # 비즈니스 레벨 채팅 세션 ID (클라이언트/DB에서 생성)
    user_id: Optional[str] = None      # 인증된 사용자 ID (JWT 등에서 추출)
    model: Optional[str] = None        # OpenAI 모델명 (예: "gpt-4o", "gpt-4o-mini"). None이면 환경변수 CHATGPT_MODEL_NAME 사용

    class Config:
        schema_extra = {
            "example": {
                "user_input": '{"persona_id": "PERSONA_002", "purpose": "신상품홍보", "product_categories": ["립스틱"]}',
                "session_id": "sess_abc123",
                "user_id": "user_001",
                "model": "gpt-4o-mini"
            }
        }


class ProductSelection(BaseModel):
    """제품 선택 요청"""
    thread_id: str                      # LangGraph 내부 thread ID (/generate 응답에서 받은 값)
    selected_product_id: str
    session_id: Optional[str] = None   # 비즈니스 레벨 세션 ID (로깅/추적용)
    user_id: Optional[str] = None      # 인증된 사용자 ID (로깅/추적용)
    model: Optional[str] = None        # /generate 호출 시 사용한 모델과 동일한 값을 전달

    class Config:
        schema_extra = {
            "example": {
                "thread_id": "uuid-aaa-bbb-ccc",
                "selected_product_id": "PROD001",
                "session_id": "sess_abc123",
                "user_id": "user_001",
                "model": "gpt-4o-mini"
            }
        }


class CRMResponse(BaseModel):
    """CRM 메시지 생성 응답"""
    status: Literal["needs_selection", "completed", "error"]
    thread_id: str                                          # LangGraph 내부 ID (select-product 재개용)
    session_id: Optional[str] = None                       # 비즈니스 레벨 세션 ID
    recommended_products: Optional[List[Dict[str, Any]]] = None
    persona_info: Optional[Dict[str, Any]] = None
    search_query: Optional[str] = None
    count: Optional[int] = None
    final_message: Optional[Any] = None
    selected_product: Optional[Dict[str, Any]] = None
    regeneration_history: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


# ============================================================
# 엔드포인트
# ============================================================

@router.post("/generate", response_model=CRMResponse)
async def generate_crm_message(request: CRMRequest):
    """
    1단계: CRM 메시지 생성 시작

    - 워크플로우를 통해 사용자 요청 파싱 및 상품 추천
    - 추천 제품 목록 반환 (Human-in-the-loop)
    - 사용자가 제품을 선택할 때까지 대기
    """
    try:
        agent = get_agent()
        set_agent_name("crm_agent")

        logger.info(
            "generate_started",
            thread_id=request.thread_id,
            input_length=len(request.user_input),
        )

        result = await agent.run(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=request.user_id,
            model=request.model,
        )

        # CRMAgent의 응답을 CRMResponse 형식으로 변환
        status = "needs_selection" if result.get("status") == "waiting_for_user" else \
                 "completed" if result.get("status") == "completed" else "error"

        logger.info(
            "generate_completed",
            status=status,
            thread_id=result.get("thread_id"),
            product_count=len(result.get("recommended_products", [])),
        )

        return CRMResponse(
            status=status,
            thread_id=result.get("thread_id"),
            session_id=result.get("session_id"),
            recommended_products=result.get("recommended_products"),
            persona_info=result.get("persona_info"),
            search_query=None,
            count=len(result.get("recommended_products", [])) if result.get("recommended_products") else None,
            final_message=result.get("messages"),
            selected_product=None,
            regeneration_history=result.get("regeneration_history"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error("generate_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/select-product", response_model=CRMResponse)
async def select_product(request: ProductSelection):
    """
    2단계: 사용자 제품 선택 처리

    - 선택한 제품의 상품 ID로 워크플로우 재개
    - create_product_message_node 실행
    - 최종 CRM 메시지 생성 완료
    """
    try:
        agent = get_agent()
        set_agent_name("crm_agent")

        logger.info(
            "select_product_started",
            thread_id=request.thread_id,
            selected_product_id=request.selected_product_id,
        )

        result = await agent.resume_with_selection(
            thread_id=request.thread_id,
            selected_product_id=request.selected_product_id,
            session_id=request.session_id,
            user_id=request.user_id,
            model=request.model,
        )

        # CRMAgent의 응답을 CRMResponse 형식으로 변환
        status = "completed" if result.get("status") == "completed" else "error"

        # 선택된 상품 정보 추출
        selected_product = None
        messages = result.get("messages", [])
        if messages:
            msg = messages[0]
            selected_product = {
                "product_id": msg.get("product_id"),
                "product_name": msg.get("product_name"),
                "brand": msg.get("brand"),
                "sale_price": msg.get("sale_price")
            }

        logger.info(
            "select_product_completed",
            status=status,
            thread_id=request.thread_id,
            message_count=len(messages),
        )

        return CRMResponse(
            status=status,
            thread_id=result.get("thread_id"),
            session_id=result.get("session_id"),
            recommended_products=result.get("recommended_products"),
            persona_info=result.get("persona_info"),
            search_query=None,
            count=len(result.get("recommended_products", [])) if result.get("recommended_products") else None,
            final_message=messages,
            selected_product=selected_product,
            regeneration_history=result.get("regeneration_history"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(
            "select_product_failed",
            thread_id=request.thread_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "ok", "message": "CRM API is running"}
