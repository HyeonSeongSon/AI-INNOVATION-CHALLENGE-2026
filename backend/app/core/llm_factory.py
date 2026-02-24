"""
LLM 팩토리

모델명 접두사로 제공자를 자동 판별하여 LangChain LLM 인스턴스를 반환한다.

지원 제공자:
- OpenAI  : gpt-*, o1-*, o3-*
- Anthropic: claude-*
- Google  : gemini-*
"""

import os
from langchain_core.language_models import BaseChatModel


def create_llm(model_name: str, temperature: float = 0, **kwargs) -> BaseChatModel:
    """
    모델명으로 LLM 인스턴스 생성

    Args:
        model_name: 모델명. 접두사로 제공자를 자동 판별한다.
                    - "gpt-4o", "gpt-4o-mini", "o1", "o3-mini" → OpenAI
                    - "claude-opus-4-6", "claude-sonnet-4-6"    → Anthropic
                    - "gemini-2.0-flash", "gemini-1.5-pro"      → Google
        temperature: 생성 온도. 제공자별로 허용 범위가 다를 수 있으니 주의.
        **kwargs   : 제공자별 추가 파라미터 (timeout, max_tokens 등)

    Returns:
        BaseChatModel: LangChain 공통 인터페이스 LLM 인스턴스

    Raises:
        ValueError: 지원하지 않는 모델명 접두사
    """
    if model_name.startswith(("gpt-", "o1", "o3", "o4")):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=temperature, **kwargs)

    elif model_name.startswith("claude-"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name, temperature=temperature, **kwargs)

    elif model_name.startswith("gemini-"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, **kwargs)

    else:
        raise ValueError(
            f"지원하지 않는 모델명: '{model_name}'. "
            "지원 접두사: gpt-*, o1*, o3*, o4*, claude-*, gemini-*"
        )
