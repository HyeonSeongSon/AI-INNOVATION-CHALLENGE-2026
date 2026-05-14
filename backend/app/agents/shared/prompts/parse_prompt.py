def build_generate_message_router_prompt() -> str:
    """대화 히스토리를 보고 인텐트를 판단하여 다음 노드와 노드별 데이터를 한 번에 반환하는 프롬프트."""
    return """대화 히스토리를 분석하여 사용자의 인텐트를 판단하고, 다음 노드와 필요한 데이터를 반환하세요.

**[Step 1] 인텐트 판단 → next_node 결정**

다음 조건을 순서대로 확인하세요:

- **message_feedback_node**: 대화 히스토리에 AI가 생성한 CRM 메시지("[상품ID: ... | 브랜드: ... | 목적: ...]" 형식)가 존재하고,
  마지막 사용자 메시지가 해당 메시지에 대한 수정/피드백 요청인 경우
  (예: "톤을 바꿔줘", "더 짧게", "제목 수정", "다르게 써줘", "이 부분 고쳐줘")

- **generate_message_node**: 그 외 모든 경우 (처음 생성 요청, 재시도 요청 포함)
  재시도("다시 만들어줘", "재시도", "다시 해줘")는 이전 대화에서 product_id/purpose를 그대로 재추출

**[Step 2] next_node에 맞는 필드만 채우기**

**next_node == "generate_message_node" 인 경우:**
- `tasks` 필드를 채우고, `feedback_input`은 null
- tasks 규칙:
  - 사용자가 수량·순위를 지정한 경우 해당 상품만 선택 (아래 예시 참고)
    - "스코어가 가장 높은", "TOP1", "가장 좋은 하나", "최고 상품" → 추천 목록에서 [TOP1] 상품 1개만 task
    - "상위 2개", "TOP1·TOP2" → [TOP1], [TOP2] 상품 2개만 task
  - 수량·순위 지정이 없고 상품이 여러 개 언급된 경우 각 상품마다 별도 task로 분리
  - 하나의 purpose가 여러 상품에 공통 적용되면 각 task에 동일한 purpose 설정
  - 상품마다 다른 purpose가 명시된 경우 각각의 purpose 적용

**next_node == "message_feedback_node" 인 경우:**
- `feedback_input` 필드를 채우고, `tasks`는 null
- feedback_input 추출 방법:
  - title, message, product_id: 히스토리 내 AI 생성 CRM 메시지("[상품ID: p001 | 브랜드: ... | 목적: ...]\\n제목: ...\\n내용: ..." 형식)에서 추출
  - feedback: 마지막 사용자 메시지의 수정 요청 내용
  - purpose: AI 메시지의 "목적:" 항목 또는 마지막 사용자 메시지에서 추출 (명시 없으면 null)
  - title, message, product_id, feedback 는 반드시 추출
  - 여러 상품이 있는 경우 마지막 사용자 메시지가 언급하는 상품의 메시지를 추출

**[필수] purpose 허용값 — 아래 7개 문자열 중 정확히 하나만 출력. 띄어쓰기와 슬래시(/) 포함 완전 일치. 변형·축약·번역 절대 불가.**

"브랜드/제품 첫소개"
"신제품 홍보"
"베스트셀러 제품 소개"
"프로모션/이벤트 소개"
"성분/효능 강조 소개"
"피부타입/고민 강조 소개"
"라이프스타일/연령대 강조 소개"

키워드 → purpose 매핑:

1. "브랜드/제품 첫소개" (기본값)
   - 키워드: 소개, 광고, 홍보, 추천, 안내 (다른 특정 목적이 없을 때)

2. "신제품 홍보"
   - 키워드: 신제품, 신상품, 새로운, NEW, 런칭, 출시, 리뉴얼

3. "베스트셀러 제품 소개"
   - 키워드: 베스트셀러, 베스트, 인기제품, 스테디셀러, 판매1위, 인기상품

4. "프로모션/이벤트 소개"
   - 키워드: 프로모션, 이벤트, 할인, 특가, 세일, 행사, 기획전

5. "성분/효능 강조 소개"
   - 키워드: 성분, 효능, 효과, 기능, 레티놀, 히알루론산, 나이아신아마이드, 성분강조, 효능강조, 효능중심

6. "피부타입/고민 강조 소개"
   - 키워드: 건성, 지성, 복합성, 민감성, 여드름, 주름, 미백, 트러블, 모공

7. "라이프스타일/연령대 강조 소개"
   - 키워드: 20대, 30대, 40대, 직장인, 학생, 주부, 바쁜, 간편한

**예시:**

입력: "p001 상품으로 프로모션 메시지 만들어줘"
출력: {"next_node": "generate_message_node", "tasks": [{"product_id": "p001", "purpose": "프로모션/이벤트 소개"}], "feedback_input": null}

입력: (AI가 p001 메시지 생성 후) "톤을 더 부드럽게 바꿔줘"
출력: {"next_node": "message_feedback_node", "tasks": null, "feedback_input": {"title": "...", "message": "...", "product_id": "p001", "feedback": "톤을 더 부드럽게 바꿔줘", "purpose": "..."}}

입력: "다시 만들어줘"
출력: {"next_node": "generate_message_node", "tasks": [{"product_id": "<이전 대화의 product_id>", "purpose": "<이전 대화의 purpose>"}], "feedback_input": null}

**persona_id 추출:**
- 대화에서 페르소나 ID(예: 'P001', 'PERSONA_ABC123')가 명시된 경우 `persona_id`에 채움
- 언급이 없으면 null
"""


def build_crm_parse_prompt(categories) -> str:
    """
    사용자 요청에서 페르소나id, 브랜드, 상품 카테고리를 파싱하는 프롬프트

    Args:
        categories: 상품 카테고리 리스트

    Returns:
        prompt
    """
   #  categories_list = "\n".join(f"- {c}" for c in categories)

    return f"""대화 히스토리를 분석하여 CRM 상품 추천 요청을 파싱하고 JSON으로 반환하세요.

**출력 필드:** persona_id(단일), brands(리스트), product_categories(리스트), purpose(단일), exclusive_target(단일/None), has_persona_info(bool)
**JSON 입력:** 필드를 그대로 매핑. 자연어 입력: 키워드 분석하여 변환.
**persona_id:** PERSONA_[숫자+대문자영어] 형식으로 정규화 (예: "6E6354965AB9" → "PERSONA_6E6354965AB9")
**persona_id 추출 규칙:** 입력 메시지에서만 추출한다. 메시지에 persona_id가 없으면 None을 반환한다. 이전 대화의 persona_id를 끌어오지 않는다.
**has_persona_info 규칙:** 입력 메시지에 페르소나 관련 정보가 포함되어 있으면 True, 없으면 False.
- True: persona_id가 있거나, 피부타입/나이/직업/피부고민/라이프스타일 등 자연어 페르소나 설명이 포함된 경우
- False: 제품명/카테고리/브랜드만 언급되고 페르소나 정보가 전혀 없는 경우 (예: "클렌징 오일로 추천해줘", "이니스프리 제품으로 바꿔줘")
**brands:** 사용자가 입력에서 명시적으로 언급한 브랜드명만 추출. 언급이 없으면 반드시 []로 반환. 카테고리나 맥락에서 유추하거나 추가하지 말 것.

**product_categories - 반드시 아래 목록에서만 선택:**
{categories}
사용자가 명시적으로 언급한 카테고리만 추출. 언급하지 않은 관련 카테고리를 임의로 추가하지 말 것.
키워드 정규화(예: "스킨"→"스킨&토너", "앰플"→"앰플")는 허용하되, 그 외 카테고리 확장 금지.
세트 상품은 사용자가 명시적으로 "세트"라고 언급한 경우에만 포함.

빈 리스트는 []로 반환.
"""