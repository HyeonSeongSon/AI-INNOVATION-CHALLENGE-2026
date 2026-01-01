"""
CRM 메시지 요청 파싱 Tool
자연어, ID 직접 입력, JSON 형태 모두 지원
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import json

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))


# ============================================================
# 다중 값 지원 스키마
# ============================================================

class MultiMessageRequest(BaseModel):
    """다중 값을 지원하는 CRM 메시지 요청"""

    persona_id: Optional[str] = Field(
        default=None,
        description="페르소나 ID (단일 값). 예: 'P123' 또는 '20대 여성'"
    )

    purpose: Optional[str] = Field(
        default=None,
        description="메시지 목적 (단일 값). 예: '프로모션', '재구매유도'"
    )

    product_categories: List[str] = Field(
        default_factory=list,
        description="상품 카테고리 리스트. 예: ['스킨케어', '메이크업', '헤어케어']"
    )

    brands: List[str] = Field(
        default_factory=list,
        description="브랜드 리스트. 예: ['라네즈', '설화수', '이니스프리']"
    )

    exclusive_target: Optional[str] = Field(
        default=None,
        description="특정 대상 전용 제품 (단일 값). 예: '남성', '반려동물', '베이비', '임산부' 등. 없으면 None"
    )


# ============================================================
# 파싱 Tool
# ============================================================

class MultiValueParser:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY가 설정되지 않았습니다. "
                "backend/app/.env 파일에 OPENAI_API_KEY를 설정해주세요."
            )

        self.llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
        self.parser = self.llm.with_structured_output(MultiMessageRequest)
        print(f"[INFO] OpenAI API 연결 완료")

    def parse(self, user_input: str) -> MultiMessageRequest:
        """자연어 → 다중 값 파싱"""

        system_prompt = """
당신은 CRM 메시지 요청을 파싱하는 전문가입니다.

**중요 규칙:**
1. 페르소나와 목적은 단일 값 (문자열)
2. 브랜드와 카테고리는 여러 개 가능 (리스트)
3. 특정 대상 전용 제품은 단일 값 (문자열)
4. JSON 형태로 입력되면 그대로 파싱

**입력 형태:**
- 자연어: "20대 여성에게 라네즈, 설화수 스킨케어 프로모션 메시지"
- JSON: {"persona_id": "A20250001", "brands": ["라네즈"], "product_categories": ["스킨케어"]}

**파싱 규칙:**
- "라네즈, 설화수, 이니스프리" → brands: ["라네즈", "설화수", "이니스프리"]
- "스킨케어와 메이크업" → product_categories: ["스킨케어", "메이크업"]
- JSON 입력 시 → 필드를 그대로 매핑

**목적(purpose) 매핑 (반드시 다음 2개 중 하나로만 선택):**
- "신상품", "신제품", "새로운 제품", "NEW", "런칭", "출시", "신규" 등 **새로 나온 제품**과 관련된 키워드가 명확히 있으면 → purpose: "신제품홍보"
- 그 외 모든 경우 (제품홍보, 브랜드홍보, 제품소개, 브랜드소개, 광고, 알림, 프로모션, 할인, 이벤트, 특가, 세일, 재구매유도 등) → purpose: "브랜드/제품 소개"
- 목적이 명확하지 않거나 언급이 없으면 → purpose: "브랜드/제품 소개" (기본값)

**중요**: 사용자가 입력한 텍스트를 그대로 추출하지 말고, 입력의 의도를 분석하여 위 2개 중 하나로 반드시 매핑하세요.
예시:
  - "제품홍보 목적으로" → purpose: "브랜드/제품 소개"
  - "신제품 출시 알림" → purpose: "신제품홍보"
  - "프로모션 메시지" → purpose: "브랜드/제품 소개"

**페르소나 매핑 (단일 값만):**
- "P123", "P456", "P789" 등 ID 형식이면 → 그대로 사용 (예: "P123" → persona_id: "P123")
- "20대 여성" → persona_id: "P123"
- "30대 남성" → persona_id: "P456"
- "40대 여성" → persona_id: "P789"

**특정 대상 전용 제품 매핑:**
- "남성전용", "남성용", "남성제품" → exclusive_target: "남성"
- "반려동물", "펫", "애완동물" → exclusive_target: "반려동물"
- "베이비", "아기", "유아", "아기도 사용" → exclusive_target: "베이비"
- "임산부", "임신부", "산모" → exclusive_target: "임산부"
- "시니어", "노인", "어르신" → exclusive_target: "시니어"
- 해당 사항 없으면 → exclusive_target: None

리스트가 비어있으면 빈 리스트 []를 반환하세요.
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ]

        return self.parser.invoke(messages)


# ============================================================
# Tool 함수
# ============================================================

# 전역 파서 인스턴스 (재사용)
_parser_instance = None

def _get_parser():
    """파서 인스턴스 가져오기 (싱글톤)"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = MultiValueParser()
    return _parser_instance


@tool
def parse_crm_message_request(user_input: str) -> Dict[str, Any]:
    """
    사용자의 CRM 메시지 생성 요청을 구조화된 데이터로 파싱합니다.

    **언제 사용하나요?**
    - 사용자가 자연어, JSON, 또는 비구조화된 형태로 CRM 메시지 생성을 요청했을 때
    - persona_id, purpose, brands, product_categories 같은 정보를 추출해야 할 때
    - 아직 페르소나 정보나 캠페인 조건이 구조화되지 않은 상태일 때

    **입력 형태:**
    - 자연어: "20대 건성피부 고객에게 설화수 크림 추천해줘"
    - JSON: {"persona_id": "PERSONA_002", "brands": ["설화수"], "product_categories": ["크림"]}

    Args:
        user_input: 사용자 입력 (자연어, JSON 등)

    Returns:
        파싱된 결과 딕셔너리:
        {
            "persona_id": "PERSONA_002",
            "purpose": "신상품홍보",
            "brands": ["설화수"],
            "product_categories": ["크림"],
            "exclusive_target": None,
            "persona_info": {...}  # 페르소나 상세 정보 포함
        }
    """
    parser = _get_parser()
    parsed = parser.parse(user_input)
    return parsed.model_dump()


# ============================================================
# 테스트
# ============================================================


if __name__ == "__main__":
    print("=== 다중 값 파싱 테스트 ===\n")

    parser = MultiValueParser()

    test_cases = [
        # 테스트 1: 여러 브랜드
        {
            "input": "20대 여성 페르소나로 라네즈, 마녀공장, 이니스프리 스킨케어 프로모션 메시지",
            "description": "여러 브랜드"
        },

        # 테스트 2: 여러 카테고리
        {
            "input": "마녀공장 스킨케어, 메이크업, 헤어케어 프로모션 메시지. 20대 여성",
            "description": "여러 카테고리"
        },

        # 테스트 3: 브랜드 + 카테고리 조합
        {
            "input": "마녀공장, 설화수 브랜드의 스킨케어, 메이크업 프로모션. 남성제품",
            "description": "브랜드 x 카테고리 조합"
        },

        # 테스트 4: 페르소나 ID 직접 입력
        {
            "input": "P123 페르소나로 라네즈 스킨케어 프로모션 메시지",
            "description": "페르소나 ID 직접 입력"
        },

        # 테스트 5: 페르소나 ID + 여러 브랜드
        {
            "input": "P456 타겟으로 라네즈, 설화수 메이크업 재구매유도",
            "description": "페르소나 ID + 여러 브랜드"
        },

        # 테스트 6: JSON 형태 - 페르소나 ID만
        {
            "input": """{
                "persona_id": "A20250001"
            }""",
            "description": "JSON 형태 - 페르소나 ID만"
        },

        # 테스트 7: JSON 형태 - 전체 필드
        {
            "input": """{
                "persona_id": "A20250001",
                "purpose": "프로모션",
                "brands": ["라네즈", "설화수"],
                "product_categories": ["스킨케어", "메이크업"],
                "exclusive_target": "남성"
            }""",
            "description": "JSON 형태 - 전체 필드"
        },

        # 테스트 8: JSON 형태 - 일부 필드만
        {
            "input": """{
                "persona_id": "P123",
                "brands": ["마녀공장", "이니스프리"],
                "product_categories": ["스킨케어"]
            }""",
            "description": "JSON 형태 - 일부 필드"
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print("=" * 80)
        print(f"\n[테스트 {i}] {test_case['description']}")
        print(f"입력: \"{test_case['input']}\"")
        print("-" * 80)

        # 파싱
        parsed = parser.parse(test_case['input'])

        print(f"\n[파싱 결과]")
        print(parsed)