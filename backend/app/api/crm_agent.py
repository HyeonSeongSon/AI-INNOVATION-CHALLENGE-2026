"""
CRM Agent API 엔드포인트
웹 환경에서 인터럽트 기반 상품 추천 및 메시지 생성을 처리
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json

# 세션 저장소 (프로덕션에서는 Redis 사용 권장)
sessions: Dict[str, Dict[str, Any]] = {}

router = APIRouter(prefix="/api/crm", tags=["CRM Agent"])


# ============================================================
# Request/Response 모델
# ============================================================

class StartRequest(BaseModel):
    """상품 추천 시작 요청"""
    user_message: str  # 사용자 채팅 입력

    class Config:
        json_schema_extra = {
            "example": {
                "user_message": "PERSONA_002로 신상품 홍보용 립스틱 광고 만들어줘"
            }
        }


class Product(BaseModel):
    """상품 정보"""
    상품명: str
    브랜드: str
    판매가: Any  # int or str
    할인율: Optional[float] = 0
    별점: Optional[float] = None
    리뷰_갯수: Optional[int] = 0
    vector_search_score: Optional[float] = None
    상품ID: Optional[str] = None
    카테고리: Optional[str] = None


class StartResponse(BaseModel):
    """상품 추천 응답"""
    session_id: str
    products: List[Dict[str, Any]]

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "products": [
                    {
                        "상품명": "노웨어 립스틱 바밍글로우",
                        "브랜드": "에스쁘아",
                        "판매가": 20400,
                        "할인율": 15,
                        "별점": 4.8,
                        "리뷰_갯수": 1428
                    }
                ]
            }
        }


class SelectRequest(BaseModel):
    """상품 선택 요청"""
    session_id: str
    selected_index: int

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "selected_index": 0
            }
        }


class MessageResponse(BaseModel):
    """메시지 생성 응답"""
    title: str
    message: str
    selected_product: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "title": "건조한 입술, 이제 촉촉하게",
                "message": "입술이 자주 갈라지시나요? 에스쁘아 노웨어 립스틱...",
                "selected_product": {
                    "상품명": "노웨어 립스틱 바밍글로우",
                    "브랜드": "에스쁘아"
                }
            }
        }


# ============================================================
# 헬퍼 함수
# ============================================================

def extract_interrupted_data(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Agent 실행 결과에서 인터럽트 데이터 추출

    Args:
        result: agent.generate()의 반환값

    Returns:
        인터럽트 데이터 또는 None
    """
    messages = result.get('raw_result', {}).get('messages', [])

    for msg in messages:
        if msg.__class__.__name__ == "ToolMessage":
            try:
                tool_result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(tool_result, dict) and tool_result.get('status') == 'interrupted':
                    return tool_result
            except:
                pass

    return None


def extract_parsed_request(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Agent 실행 결과에서 파싱된 요청 데이터 추출

    Args:
        result: agent.generate()의 반환값

    Returns:
        파싱된 요청 데이터 또는 None
    """
    messages = result.get('raw_result', {}).get('messages', [])

    for msg in messages:
        if msg.__class__.__name__ == "ToolMessage":
            try:
                tool_result = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(tool_result, dict) and "persona_id" in tool_result:
                    return tool_result
            except:
                pass

    return None


# ============================================================
# API 엔드포인트
# ============================================================

@router.post("/start", response_model=StartResponse)
def start_recommendation(request: StartRequest):
    """
    1단계: 상품 추천 시작

    - 사용자 메시지를 분석하여 상품 추천
    - 추천된 3개 상품과 세션 ID 반환
    - 세션 ID는 2단계 요청 시 사용
    """
    try:
        # Agent 임포트 (lazy import)
        from app.service.agent.message_agent.crm_message_agent import CRMMessageHierarchicalAgent

        # Agent 실행
        agent = CRMMessageHierarchicalAgent()
        result = agent.generate(user_request=request.user_message)

        # 인터럽트 데이터 추출
        interrupted_data = extract_interrupted_data(result)

        if not interrupted_data:
            raise HTTPException(
                status_code=500,
                detail="상품 추천 실패: 인터럽트 데이터를 찾을 수 없습니다"
            )

        # 파싱된 요청 데이터 추출
        parsed_request = extract_parsed_request(result)

        if not parsed_request:
            raise HTTPException(
                status_code=500,
                detail="상품 추천 실패: 파싱된 요청 데이터를 찾을 수 없습니다"
            )

        # 세션 ID 생성
        session_id = str(uuid.uuid4())

        # 세션 저장
        sessions[session_id] = {
            "thread_id": interrupted_data["thread_id"],
            "merged_products": interrupted_data["merged_products"],
            "parsed_request": parsed_request
        }

        # 응답 반환
        return StartResponse(
            session_id=session_id,
            products=interrupted_data["merged_products"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상품 추천 중 오류 발생: {str(e)}")


@router.post("/select", response_model=MessageResponse)
def select_and_generate(request: SelectRequest):
    """
    2단계: 상품 선택 및 메시지 생성

    - 사용자가 선택한 상품으로 CRM 메시지 생성
    - 생성된 메시지와 선택된 상품 정보 반환
    - 세션 자동 삭제
    """
    try:
        # 세션 조회
        session = sessions.get(request.session_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail="세션을 찾을 수 없습니다. 다시 시작해주세요."
            )

        # 선택 인덱스 검증
        merged_products = session["merged_products"]
        if not (0 <= request.selected_index < len(merged_products)):
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 상품 번호입니다. 0부터 {len(merged_products)-1} 사이의 숫자를 입력하세요."
            )

        # 도구 임포트 (lazy import)
        from app.service.agent.tools.basic_recommend_products import recommend_products
        from app.service.agent.tools.create_product_message import create_product_message

        # 상품 선택 완료
        final_result = recommend_products.invoke({
            "thread_id": session["thread_id"],
            "selected_index": request.selected_index
        })

        if final_result.get("status") != "completed":
            raise HTTPException(
                status_code=500,
                detail=f"상품 선택 실패: {final_result.get('error', '알 수 없는 오류')}"
            )

        # 메시지 생성
        message_result = create_product_message.invoke({
            "product": final_result["selected_product"],
            "persona_info": session["parsed_request"].get("persona_info", {}),
            "purpose": session["parsed_request"].get("purpose", "브랜드/제품 소개")
        })

        # 세션 삭제
        del sessions[request.session_id]

        # 응답 반환
        return MessageResponse(
            title=message_result.get("title", ""),
            message=message_result.get("message", ""),
            selected_product=final_result["selected_product"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메시지 생성 중 오류 발생: {str(e)}")


@router.get("/session/{session_id}")
def get_session_info(session_id: str):
    """
    세션 정보 조회 (디버깅용)

    - 현재 세션에 저장된 데이터 확인
    """
    session = sessions.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    return {
        "session_id": session_id,
        "has_thread_id": "thread_id" in session,
        "product_count": len(session.get("merged_products", [])),
        "has_parsed_request": "parsed_request" in session
    }


@router.delete("/session/{session_id}")
def delete_session(session_id: str):
    """
    세션 삭제

    - 사용자가 중간에 취소한 경우 세션 정리
    """
    if session_id in sessions:
        del sessions[session_id]
        return {"message": "세션이 삭제되었습니다"}

    raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")


@router.get("/sessions/count")
def get_sessions_count():
    """
    활성 세션 개수 조회 (모니터링용)
    """
    return {
        "active_sessions": len(sessions),
        "session_ids": list(sessions.keys())
    }
