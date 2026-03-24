"""
품질 검사 LLM-as-a-Judge 프롬프트

생성된 마케팅 메시지를 5가지 기준으로 평가하는 프롬프트
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
from typing import List, Dict, Any


def build_quality_check_prompt(
    brand_name: str,
    product_name: str,
    product_info: Dict[str, Any],
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
        product_info: 상품 정보 dict (concern, key_benefits, target_user 등 포함)
        purpose: 메시지 목적
        brand_tone: 브랜드 톤 가이드
        title: 평가 대상 메시지 제목
        message: 평가 대상 메시지 본문

    Returns:
        [SystemMessage, HumanMessage] 리스트
    """
    # 타깃 고객 관련 필드 추출
    concern = product_info.get("concern") or []
    key_benefits = product_info.get("key_benefits") or []
    target_user = product_info.get("target_user") or ""

    concern_text = ", ".join(concern) if concern else "정보 없음"
    key_benefits_text = "\n".join(f"- {b}" for b in key_benefits) if key_benefits else "정보 없음"

    product_summary = json.dumps(product_info, ensure_ascii=False, indent=2)

    system_prompt = """당신은 뷰티 마케팅 메시지 품질 평가 전문가입니다.
주어진 마케팅 메시지를 다음 5가지 기준으로 평가해주세요.

## 평가 기준 (각 1-5점)

### 1. 정확성 (accuracy)
- 상품 정보(이름, 브랜드, 성분 등)가 정확하게 반영되었는지
- 존재하지 않는 정보를 임의로 만들어내지 않았는지
- 5점: 모든 상품 정보가 정확 / 1점: 허위 정보 포함

### 2. 톤 (tone)
- 브랜드 톤 가이드에 부합하는지
- 브랜드 성격과 어조가 일관되는지
- 5점: 브랜드 톤 완벽 부합 / 1점: 브랜드 톤과 불일치

### 3. 개인화 (personalization)
- 상품이 타깃으로 하는 고객의 고민(concern)이 메시지에 공감되는 방식으로 반영되었는지
- 상품의 핵심 혜택(key_benefits)이 타깃 고객 관점에서 적절히 강조되었는지
- 타깃 고객 설명(target_user)에 맞는 소구 포인트를 사용했는지
- 5점: 타깃 고민과 핵심 혜택이 메시지에 최적화됨 / 1점: 타깃 고객과 무관한 일반 문구

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
{product_summary}

### 타깃 고객 고민
{concern_text}

### 핵심 혜택
{key_benefits_text}

### 타깃 고객 설명
{target_user if target_user else "정보 없음"}

### 브랜드 톤 가이드
{brand_tone}

### 메시지 목적
{purpose}"""

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]
