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

    system_prompt = """당신은 뷰티 CRM 마케팅 메시지 품질 평가 전문가입니다.
아래 5가지 기준으로 메시지를 평가하세요. 금지 표현·약사법 위반 여부는 이미 사전 검증되었으므로 평가하지 않습니다.

## 평가 기준 (각 1-5점)

### 1. 정확성 (accuracy)
제공된 [상품 정보]에 있는 사실만 사용했는지 검증합니다.
- 상품명·브랜드명이 정확히 일치하는가
- 언급된 성분·기능이 [상품 정보]에 실제로 존재하는가
- 수치·인증·임상 근거 등 [상품 정보]에 없는 내용을 임의로 추가하지 않았는가
- 5점: 모든 정보가 [상품 정보]와 일치
- 3점: 표현 방식의 차이는 있지만 사실 오류 없음
- 1점: [상품 정보]에 없는 내용이 포함됨

### 2. 톤 (tone)
[브랜드 톤 가이드]의 문체·어조가 메시지에 구현되었는지 평가합니다.
- 호칭 방식·문장 온도·리듬이 브랜드 성격과 일치하는가
- 격식체/반말/이모지 사용이 가이드와 일관되는가
- 5점: 브랜드 톤 가이드를 완벽히 구현
- 3점: 대체로 맞지만 일부 문장에서 어긋남
- 1점: 가이드와 전혀 다른 문체

### 3. 개인화 (personalization)
메시지가 타깃 고객의 상황에 맞게 작성되었는지 평가합니다.
- 타깃 고객의 고민(concern)이 공감을 유도하는 방식으로 반영되었는가
- 핵심 혜택(key_benefits)이 타깃 고객 관점에서 강조되었는가
- 타깃 고객 설명(target_user)에 맞는 소구 포인트를 사용했는가
- 5점: 고민·혜택·소구 포인트가 타깃에 최적화됨
- 3점: 일반적 혜택 위주이나 타깃과 무관하지는 않음
- 1점: 타깃과 무관한 범용 문구

### 4. 자연스러움 (naturalness)
CRM 메시지로서 읽기 좋고 행동을 유도하는 문장인지 평가합니다.
- 문장이 매끄럽고 문법 오류가 없는가
- 어색한 직역체·기계적 나열 없이 읽기 쉬운 구조인가
- 짧은 문장과 여백 활용이 모바일 가독성에 적합한가
- 5점: 전문 카피라이터 수준의 완성도
- 3점: 읽는 데 지장 없으나 일부 어색한 표현 존재
- 1점: 기계적이거나 문법 오류로 독해 방해

### 5. CTA 명확도 (cta_clarity)
메시지를 받은 소비자가 다음 행동을 명확히 알 수 있는지 평가합니다.
- 소비자가 취해야 할 행동(구매·클릭·앱 오픈 등)이 자연스럽게 안내되는가
- [메시지 목적]에 부합하는 행동 유도가 포함되어 있는가
- CTA가 강압적이지 않으면서도 동기를 부여하는가
- 5점: 행동과 이유가 설득력 있게 연결됨
- 3점: CTA는 있으나 행동 동기가 약하거나 모호함
- 1점: CTA가 없거나 목적과 전혀 무관

## 피드백 작성 규칙
- 3점 미만 항목에 대해서만 구체적인 수정 방향을 제시하세요
- 수정 방향은 "어떻게 바꾸면 되는지"를 명시하세요 (예: "~표현을 ~로 교체")
- 잘 된 부분을 1문장으로 언급하세요
- 전체 2-4문장, 한글로 작성하세요"""

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
