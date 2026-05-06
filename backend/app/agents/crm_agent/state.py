from typing import Dict, Any, Optional, List
from typing_extensions import TypedDict
from ..base.base_state import BaseState

# ============================================================
# CRM Intermediate Data 타입 정의
# ============================================================

class ParsedRequest(TypedDict, total=False):
    """파싱된 CRM 요청 데이터"""
    persona_id: str                      # 페르소나 ID (예: "PERSONA_001")
    purpose: str                         # 메시지 목적 (예: "신제품 홍보")
    category_type: Optional[str]         # 상품 카테고리 대분류 (예: "스킨케어", "색조")
    product_categories: List[str]        # 상품 카테고리 (예: ["크림"])
    brands: List[str]                    # 브랜드 리스트 (예: ["설화수"])
    exclusive_target: Optional[str]      # 독점 타겟 (선택)


class PersonaInfo(TypedDict, total=False):
    """
    페르소나 정보

    NOTE: 한글 키를 사용하는 이유
    - 외부 API (database/api_endpoints.py의 Persona 모델)에서 반환되는 데이터 구조를 그대로 반영
    - 프롬프트 생성 시 한글 키를 직접 사용하여 LLM에게 전달 (가독성 향상)
    - 변환 없이 외부 API 응답을 그대로 사용하여 매핑 레이어 불필요
    """
    persona_id: str                      # 페르소나 ID
    이름: str                            # 이름
    나이: int                            # 나이
    성별: str                            # 성별
    직업: str                            # 직업
    피부타입: List[str]                  # 피부타입
    고민_키워드: List[str]               # 고민 키워드 (피부·헤어 통합)
    퍼스널_컬러: str                     # 퍼스널 컬러
    베이스_호수: Optional[str]           # 베이스 호수
    메이크업_선호_색상: List[str]        # 메이크업 선호 색상
    선호_성분: List[str]                 # 선호 성분
    기피_성분: List[str]                 # 기피 성분
    선호_향: List[str]                   # 선호 향
    가치관: List[str]                    # 가치관/라이프스타일
    스킨케어_루틴: List[str]             # 스킨케어 루틴
    주_활동_환경: List[str]              # 주 활동 환경
    선호_제형: List[str]                 # 선호 제형(텍스처)
    헤어_타입: List[str]                 # 헤어 타입
    관심_뷰티_카테고리: List[str]        # 관심 뷰티 카테고리
    반려동물: List[str]                  # 반려동물
    수면_시간: Optional[str]             # 수면 시간
    스트레스: Optional[str]              # 스트레스 수준
    스크린_사용: Optional[str]           # 하루 스크린 사용 시간
    쇼핑_스타일: List[str]               # 쇼핑 스타일
    구매_결정_요인: List[str]            # 구매 결정 요인
    가격_민감도: Optional[str]           # 가격 민감도
    선호_브랜드: List[str]               # 선호 브랜드
    기피_브랜드: List[str]               # 기피 브랜드


class RecommendedProduct(TypedDict, total=False):
    """추천된 상품 정보"""
    product_id: str                      # 상품 ID
    product_name: str                    # 상품명
    brand: str                           # 브랜드
    sub_tag: str                         # 상품 소분류 태그
    sale_price: int                      # 판매 가격
    discount_rate: int                   # 할인율
    rating: float                        # 평점
    review_count: int                    # 리뷰 수
    skin_type: List[str]                 # 적합 피부타입
    concerns: List[str]                  # 타겟 고민
    preferred_ingredients: List[str]     # 주요 성분
    vector_search_score: float           # 벡터 검색 스코어
    product_page_url: str                # 상품 페이지 URL


class GeneratedMessage(TypedDict, total=False):
    """생성된 메시지 정보"""
    product_id: str                      # 상품 ID
    product_name: str                    # 상품명
    brand: str                           # 브랜드
    title: str                           # 메시지 제목
    message: str                         # 메시지 본문
    purpose: str                         # 메시지 목적
    vector_search_score: float           # 벡터 검색 스코어
    product_url: str                     # 상품 URL
    sale_price: int                      # 판매 가격


class QualityScore(TypedDict, total=False):
    """LLM-as-a-Judge 평가 점수"""
    accuracy: int                        # 정확성 (1-5)
    tone: int                            # 톤 적합성 (1-5)
    personalization: int                 # 개인화 (1-5)
    naturalness: int                     # 자연스러움 (1-5)
    safety: int                          # 안전성 (1-5)
    overall: float                       # 가중 평균
    feedback: str                        # LLM 피드백


class RegenerationAttempt(TypedDict, total=False):
    """
    재생성 이력 항목

    품질 검사 실패 시 해당 시도의 메시지와 피드백을 보존합니다.
    최대 retry_count(3회)만큼 항목이 쌓입니다.
    """
    attempt: int                         # 시도 번호 (1부터 시작)
    failed_message: GeneratedMessage     # 실패한 메시지 전체 (title, message 등)
    failed_stage: str                    # 실패 단계 ("rule_check" | "llm_judge" | "groundedness")
    feedback: str                        # 실패 피드백 (재생성 프롬프트에 활용)
    scores: Optional[QualityScore]       # LLM 평가 점수 (llm_judge 실패 시에만 존재)


class GroundednessResult(TypedDict, total=False):
    """Groundedness 검증 결과"""
    is_grounded: bool                    # 전체 통과 여부
    issues: List[str]                    # 발견된 문제 리스트
    checked_fields: List[str]            # 검증한 필드 목록


class QualityCheckResult(TypedDict, total=False):
    """품질 검사 전체 결과"""
    passed: bool                         # 전체 통과 여부
    failed_stage: Optional[str]          # 실패 단계 ("rule_check" | "llm_judge" | "groundedness")
    failure_reason: Optional[str]        # 실패 사유
    rule_check_passed: bool              # Stage 1 통과 여부
    rule_check_issues: List[str]         # Stage 1 발견 이슈
    llm_judge_passed: bool               # Stage 2 통과 여부
    llm_judge_scores: Optional[QualityScore]   # Stage 2 점수
    groundedness_passed: bool            # Stage 3 통과 여부
    groundedness_result: Optional[GroundednessResult]  # Stage 3 결과


# ============================================================
# Context 그룹 정의 (노드별 책임 범위 분리)
# ============================================================

class RequestContext(TypedDict, total=False):
    """
    요청 파싱 컨텍스트

    담당 노드: parse_crm_request_node
    READ: state.input
    WRITE: intermediate.request.parsed_request
    """
    parsed_request: ParsedRequest


class RecommendationContext(TypedDict, total=False):
    """
    상품 추천 컨텍스트

    담당 노드: recommend_products_node
    READ:
      - state.input
      - intermediate.request.parsed_request
    WRITE:
      - intermediate.recommendation.persona_info
      - intermediate.recommendation.analysis_result
      - intermediate.recommendation.analysis_id
      - intermediate.recommendation.queries
      - intermediate.recommendation.recommended_products
    """
    persona_info: PersonaInfo                        # 페르소나 정보
    analysis_result: Dict[str, Any]                  # 페르소나 분석 결과 (다단계 × 다차원)
    analysis_id: int                                 # 분석 ID (DB 저장 시 생성)
    queries: List[str]                               # 생성된 검색 쿼리 (멀티 쿼리)
    recommended_products: List[RecommendedProduct]   # 추천된 상품 리스트


class MessageContext(TypedDict, total=False):
    """
    메시지 생성 컨텍스트

    담당 노드: create_product_message_node
    READ:
      - intermediate.request.parsed_request (purpose)
      - intermediate.recommendation.persona_info
      - intermediate.recommendation.recommended_products
    WRITE:
      - intermediate.message.selected_product
      - intermediate.message.messages
      - intermediate.message.product_document_summary
    """
    selected_product: RecommendedProduct             # 사용자가 선택한 상품 (품질 검사에 활용)
    messages: List[GeneratedMessage]                 # 생성된 메시지 리스트
    product_document_summary: Optional[str]          # 상품 문서 요약 (메시지 생성·품질 검토 활용)


class QualityCheckContext(TypedDict, total=False):
    """
    품질 검사 컨텍스트

    담당 노드: quality_check_node
    READ:
      - intermediate.message.messages
      - intermediate.recommendation.recommended_products
      - intermediate.recommendation.persona_info
      - intermediate.request.parsed_request
    WRITE:
      - intermediate.quality_check.results
      - intermediate.quality_check.regeneration_history
      - intermediate.quality_check.retry_count
    """
    results: List[QualityCheckResult]                # 메시지별 품질 검사 결과 (최신 시도)
    regeneration_history: List[RegenerationAttempt]  # 실패 이력 (append 방식, 최대 retry_count개)
    retry_count: int                                 # 재시도 횟수 (0이 초기값, 최대 3)


class HitlContext(TypedDict, total=False):
    """
    Human-in-the-loop interrupt 결과 저장소

    각 interrupt()의 반환값을 명확한 키로 저장하여
    다중 interrupt 상황에서도 값 충돌 없이 관리합니다.

    패턴:
      1. interrupt() 호출 → GraphInterrupt (노드 중단)
      2. Command(resume=value)로 재개 → interrupt() 반환값
      3. 반환값을 해당 키에 저장 → 이후 노드에서 읽기

    추후 interrupt 추가 시 이 클래스에 키를 추가합니다.
    """
    product_selection: Optional[str]     # 사용자가 선택한 상품 ID (recommend_products_node)
    # message_approval: str              # (예시) 메시지 승인/거부 (미래 interrupt 추가 시)


class CRMIntermediate(TypedDict, total=False):
    """
    CRM Agent의 intermediate 데이터 구조

    노드별로 논리 그룹화하여 책임 범위를 명확히 함
    """
    request: RequestContext                          # 요청 파싱 결과
    recommendation: RecommendationContext            # 상품 추천 결과
    message: MessageContext                          # 메시지 생성 결과
    quality_check: QualityCheckContext               # 품질 검사 결과
    hitl: HitlContext                                # Human-in-the-loop interrupt 결과


# ============================================================
# Custom State 정의
# ============================================================

class CRMState(BaseState, total=False):
    """
    CRM Agent용 커스텀 스테이트 (단발성)

    입력: input: str (원본 CRM 요청 텍스트)

    워크플로우:
    ┌─────────────────────────────────────────────────────────┐
    │ 1. parse_crm_request_node                                │
    │    READ:  state.input                                    │
    │    WRITE: intermediate.request.parsed_request            │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ 2. recommend_products_node                               │
    │    READ:  state.input                                    │
    │           intermediate.request.parsed_request            │
    │    WRITE: intermediate.recommendation.persona_info       │
    │           intermediate.recommendation.analysis_result    │
    │           intermediate.recommendation.analysis_id        │
    │           intermediate.recommendation.queries            │
    │           intermediate.recommendation.recommended_products│
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ 3. HUMAN-IN-THE-LOOP (interrupt)                         │
    │    - 사용자에게 추천 상품 3개 제시                       │
    │    - 사용자가 1개 선택                                   │
    │    - 결과를 intermediate.hitl.product_selection에 저장   │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ 4. create_product_message_node                           │
    │    READ:  intermediate.request.parsed_request            │
    │           intermediate.recommendation.persona_info       │
    │           intermediate.recommendation.recommended_products│
    │           intermediate.hitl.product_selection            │
    │    WRITE: intermediate.message.selected_product          │
    │           intermediate.message.messages                  │
    │           intermediate.message.product_document_summary  │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ 5. quality_check_node                                    │
    │    READ:  intermediate.message.messages                  │
    │           intermediate.message.selected_product          │
    │           intermediate.message.product_document_summary  │
    │           intermediate.recommendation.persona_info       │
    │           intermediate.request.parsed_request            │
    │    WRITE: intermediate.quality_check.results             │
    └─────────────────────────────────────────────────────────┘

    사용 예시:
        # 파싱 결과 조회
        parsed_request = state["intermediate"]["request"]["parsed_request"]

        # 추천 상품 조회
        recommended_products = state["intermediate"]["recommendation"]["recommended_products"]

        # 생성된 메시지 조회
        messages = state["intermediate"]["message"]["messages"]
    """

    # 입력
    input: str                          # 사용자 원본 CRM 요청 텍스트

    # CRM 전용 필드
    intermediate: CRMIntermediate       # 타입이 명시된 intermediate 데이터
    # NOTE: interrupt() 결과는 최상위 state 필드가 아닌
    #       intermediate.hitl.*에 저장합니다. (다중 interrupt 대비)