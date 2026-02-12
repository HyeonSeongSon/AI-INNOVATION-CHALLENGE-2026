"""
품질 검사 LLM-as-a-Judge 프롬프트

생성된 마케팅 메시지를 5가지 기준으로 평가하는 프롬프트
"""

from langchain_core.messages import SystemMessage, HumanMessage
from typing import List


def build_quality_check_prompt(
    brand_name: str,
    product_name: str,
    product_info: str,
    persona_info: str,
    purpose: str,
    brand_tone: str,
    title: str,
    message: str,
) -> List:
    """
    LLM Judge 프롬프트 구성

    Args:
        brand_name: 브랜드명
        product_name: 상품명
        product_info: 포맷팅된 상품 정보
        persona_info: 포맷팅된 페르소나 정보
        purpose: 메시지 목적
        brand_tone: 브랜드 톤 가이드
        title: 평가 대상 메시지 제목
        message: 평가 대상 메시지 본문

    Returns:
        [SystemMessage, HumanMessage] 리스트
    """

    system_prompt = """당신은 뷰티 마케팅 메시지 품질 평가 전문가입니다.
주어진 마케팅 메시지를 다음 5가지 기준으로 평가해주세요.

## 평가 기준 (각 1-5점)

### 1. 정확성 (accuracy)
- 상품 정보(이름, 브랜드, 가격, 성분 등)가 정확하게 반영되었는지
- 존재하지 않는 정보를 임의로 만들어내지 않았는지
- 5점: 모든 상품 정보가 정확 / 1점: 허위 정보 포함

### 2. 톤 (tone)
- 브랜드 톤 가이드에 부합하는지
- 금지 표현을 사용하지 않았는지
- 브랜드 성격과 어조가 일관되는지
- 5점: 브랜드 톤 완벽 부합 / 1점: 브랜드 톤과 불일치

### 3. 개인화 (personalization)
- 페르소나의 특성(피부타입, 고민, 가치관 등)이 반영되었는지
- 대상 고객에게 공감을 줄 수 있는 내용인지
- 5점: 페르소나 맞춤 최적화 / 1점: 일반적 메시지

### 4. 자연스러움 (naturalness)
- 문장이 매끄럽고 자연스러운지
- 어색한 표현이나 문법 오류가 없는지
- 읽기 쉬운 구조인지
- 5점: 전문 카피라이터 수준 / 1점: 기계적 느낌

### 5. 안전성 (safety)
- 과장된 효능 표현이 없는지
- 의료적 효과를 암시하지 않는지
- 소비자를 오도할 수 있는 표현이 없는지
- 5점: 완전 안전 / 1점: 위험한 표현 포함

## 판정 기준
- 모든 항목이 3점 이상이면 passed = true
- 하나라도 3점 미만이면 passed = false

## 피드백
- 2-3문장의 한글 종합 피드백을 작성하세요
- 개선이 필요한 부분을 구체적으로 명시하세요"""

    human_prompt = f"""## 평가 대상 메시지

### 제목
{title}

### 본문
{message}

## 참고 정보

### 브랜드
{brand_name}

### 상품명
{product_name}

### 상품 정보
{product_info}

### 브랜드 톤 가이드
{brand_tone}

### 타겟 페르소나
{persona_info}

### 메시지 목적
{purpose}"""

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]
