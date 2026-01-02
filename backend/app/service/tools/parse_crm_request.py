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

# 카테고리 목록 로드
def load_categories():
    """categories.json에서 카테고리 목록 로드"""
    # 프로젝트 루트 찾기: /app 또는 로컬 개발 환경
    current_dir = os.path.dirname(__file__)

    # Docker 환경: /app/data/categories.json
    docker_path = "/app/data/categories.json"
    # 로컬 환경: backend/app/service/tools -> ../../../../data/categories.json
    local_path = os.path.join(current_dir, "../../../../data/categories.json")

    # Docker 환경 우선 시도
    if os.path.exists(docker_path):
        categories_path = docker_path
    else:
        categories_path = local_path

    with open(categories_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['categories']

VALID_CATEGORIES = load_categories()


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

        # 카테고리 목록을 프롬프트에 포함
        categories_list = "\n".join([f"  - {cat}" for cat in VALID_CATEGORIES])

        system_prompt = f"""
당신은 CRM 메시지 요청을 파싱하는 전문가입니다.

**중요 규칙:**
1. 페르소나와 목적은 단일 값 (문자열)
2. 브랜드와 카테고리는 여러 개 가능 (리스트)
3. 특정 대상 전용 제품은 단일 값 (문자열)
4. JSON 형태로 입력되면 그대로 파싱

**입력 형태:**
- 자연어: "20대 여성에게 라네즈, 설화수 스킨케어 프로모션 메시지"
- JSON: {{"persona_id": "A20250001", "brands": ["라네즈"], "product_categories": ["스킨&토너"]}}

**파싱 규칙:**
- "라네즈, 설화수, 이니스프리" → brands: ["라네즈", "설화수", "이니스프리"]
- JSON 입력 시 → 필드를 그대로 매핑

**목적(purpose) 매핑 - 절대 규칙:**
**경고: purpose 필드는 반드시 다음 7개 값 중 정확히 하나만 사용해야 합니다. 다른 값은 절대 사용 불가합니다.**

허용된 값 및 키워드 매핑:

1. "브랜드/제품 첫소개" (기본값)
   - 키워드: 소개, 광고, 홍보, 추천, 안내 (다른 특정 목적이 없을 때)
   - 예: "제품홍보", "브랜드소개", "광고메시지", "추천메시지"

2. "신제품 홍보"
   - 키워드: 신제품, 신상품, 새로운, NEW, 런칭, 출시, 리뉴얼
   - 예: "신제품홍보", "신상품소개", "NEW 출시", "런칭메시지"

3. "베스트셀러 제품 소개"
   - 키워드: 베스트셀러, 베스트, 인기제품, 스테디셀러, 판매1위, 인기상품
   - 예: "베스트상품", "인기제품소개", "판매1위추천"

4. "프로모션/이벤트 소개"
   - 키워드: 프로모션, 이벤트, 할인, 특가, 세일, 행사, 기획전
   - 예: "프로모션소개", "이벤트메시지", "할인안내", "특가홍보", "세일광고"

5. "성분/효능 강조 소개"
   - 키워드: 성분, 효능, 효과, 기능, 레티놀, 히알루론산, 나이아신아마이드 등 성분명
   - 예: "성분강조", "효능중심", "히알루론산제품"

6. "피부타입/고민 강조 소개"
   - 키워드: 건성, 지성, 복합성, 민감성, 여드름, 주름, 미백, 트러블, 모공
   - 예: "건성피부용", "여드름케어", "미백제품"

7. "라이프스타일/연령대 강조 소개"
   - 키워드: 20대, 30대, 40대, 직장인, 학생, 주부, 바쁜, 간편한
   - 예: "30대직장인용", "바쁜아침", "학생추천"

**중요 매핑 규칙:**
- ❌ 사용자 입력을 절대 그대로 복사하지 마세요
- ✅ 키워드를 분석하여 위 7개 값 중 하나로 정확히 변환
- ✅ 여러 목적이 섞여있으면 가장 강한 키워드 우선 (프로모션 > 신제품 > 베스트셀러 > 기타)
- ✅ 애매하면 기본값인 "브랜드/제품 첫소개" 사용

**매핑 예시 (반드시 준수):**
  - "제품홍보" → "브랜드/제품 첫소개"
  - "프로모션소개" → "프로모션/이벤트 강조 소개" (❌ "프로모션소개" 아님)
  - "프로모션 목적" → "프로모션/이벤트 강조 소개"
  - "할인메시지" → "프로모션/이벤트 강조 소개"
  - "신제품 출시" → "신제품 홍보"
  - "베스트 상품" → "베스트셀러 제품 소개"
  - "히알루론산 강조" → "성분/효능 강조 소개"
  - "건성피부용" → "피부타입/고민 강조 소개"
  - "30대 타겟" → "라이프스타일/연령대 강조 소개"
  - "에스쁘아 립스틱 광고" → "브랜드/제품 첫소개"

**페르소나 매핑 (단일 값만):**
- "P123", "P456", "P789" 등 ID 형식이면 → 그대로 사용 (예: "P123" → persona_id: "P123")
- "20대 여성" → persona_id: "P123"
- "30대 남성" → persona_id: "P456"
- "40대 여성" → persona_id: "P789"

**상품 카테고리(product_categories) 매핑 - 절대 규칙:**
**경고: product_categories는 반드시 아래 허용된 카테고리 목록 중에서만 선택해야 합니다.**

**허용된 카테고리 목록 (반드시 이 중에서만 선택):**
{categories_list}

**매핑 규칙:**
1. ❌ 위 목록에 없는 카테고리는 절대 사용 불가
2. ✅ 사용자 입력을 분석하여 위 목록에서 가장 관련 있는 카테고리 선택
3. ✅ 대분류로 입력된 경우 → 해당하는 구체적 카테고리들로 변환

**대분류 → 구체적 카테고리 변환 예시:**
- "메이크업", "색조화장품" → 문맥 분석:
  - 입술 관련 → ["립스틱", "립글로스", "립틴트"]
  - 눈 관련 → ["아이섀도우", "아이라이너", "마스카라"]
  - 베이스 관련 → ["파운데이션", "쿠션", "컨실러"]
  - 구체적 제품 없으면 → ["립스틱", "아이섀도우", "파운데이션"]

- "스킨케어", "기초화장품" → 문맥 분석:
  - 토너 관련 → ["스킨&토너"]
  - 세럼 관련 → ["에센스&세럼", "앰플"]
  - 크림 관련 → ["크림", "로션&에멀젼"]
  - 구체적 제품 없으면 → ["스킨&토너", "에센스&세럼", "크림"]

- "헤어케어", "헤어" → ["샴푸", "린스&컨디셔너", "트리트먼트&팩"]
- "바디케어", "바디" → ["바디워시", "바디모이스처라이저", "바디스크럽"]
- "클렌징" → ["클렌징 폼", "클렌징 오일", "클렌징 워터"]
- "선케어", "자외선차단" → ["선블럭", "선스프레이", "선스틱"]

**브랜드별 대표 상품 참고:**
- 에스쁘아: ["립스틱", "아이섀도우", "쿠션"]
- 라네즈: ["크림", "스킨&토너", "마스크&팩"]
- 설화수: ["에센스&세럼", "크림", "스킨&토너"]
- 이니스프리: ["스킨&토너", "에센스&세럼", "마스크&팩"]
- VDIVOV: ["아이섀도우", "립스틱", "마스카라"]

**매핑 예시:**
- "에스쁘아 립스틱" → ["립스틱"]
- "라네즈 메이크업" → ["립스틱", "아이섀도우", "파운데이션"]
- "설화수 스킨케어" → ["스킨&토너", "에센스&세럼", "크림"]
- "이니스프리 그린티 토너" → ["스킨&토너"]
- "클렌징 제품" → ["클렌징 폼", "클렌징 오일"]
- "선크림" → ["선블럭"]

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
    print("======파싱결과======")
    print(parsed)
    print("====================")
    return parsed.model_dump()