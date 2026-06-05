from langchain_core.messages import SystemMessage

_SUMMARY_BASE_INSTRUCTION = """\
당신은 CRM 마케팅 에이전트의 대화 요약 담당입니다.
아래 대화 내역을 분석하여 다음 항목을 포함한 구조화된 요약을 작성하세요.

## 요약 항목 (해당 정보가 있을 때만 작성)

**[페르소나]**
- 확정된 페르소나 ID (예: PERSONA_001)
- 주요 특성 (피부타입, 주요 고민, 가치관 등 대화에서 언급된 것)

**[수행한 작업]**
- 조회/검색: 조회한 페르소나 조건, 브랜드, 카테고리
- 상품 추천: 추천된 상품명·브랜드 (최대 3개)
- 메시지 생성: 생성된 메시지 타입(문자/앱푸시 등), 핵심 내용 한 줄 요약
- 데이터 등록: 등록한 항목 종류 및 건수

**[사용자 선호 및 피드백]**
- 톤/스타일 선호 (예: 친근한 톤, 격식체, 이모지 사용 등)
- 수정 요청 내용 및 반영 여부

**[미완료 / 다음 단계]**
- 사용자가 언급했으나 아직 처리되지 않은 요청

## 작성 규칙
- 한국어로 작성
- 각 항목은 정보가 있을 때만 포함 (없으면 항목 자체를 생략)
- 불필요한 서술 없이 핵심 정보만 간결하게
- 전체 500자 이내
"""

_SUMMARY_UPDATE_PRE = """\
기존 요약을 아래 새 대화 내역으로 업데이트하세요.
변경된 내용은 덮어쓰고, 새로 추가된 정보는 병합하세요.
삭제된 메시지의 정보도 기존 요약에 이미 반영되어 있으므로 유지하세요.

## 기존 요약
"""

_SUMMARY_UPDATE_POST = """\

## 업데이트 규칙
- 페르소나가 변경됐으면 교체, 동일하면 유지
- 새로 수행한 작업은 [수행한 작업]에 추가
- 사용자 선호·피드백이 추가됐으면 병합
- 이미 처리된 항목은 [미완료]에서 제거
- 전체 500자 이내 유지

"""


def build_summary_prompt(messages: list, existing_summary: str = "") -> list:
    if existing_summary:
        instruction = _SUMMARY_UPDATE_PRE + existing_summary + _SUMMARY_UPDATE_POST + _SUMMARY_BASE_INSTRUCTION
    else:
        instruction = _SUMMARY_BASE_INSTRUCTION
    return [SystemMessage(content=instruction)] + messages
