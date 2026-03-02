"""
LLM 팩토리

모델명 접두사로 제공자를 자동 판별하여 LangChain LLM 인스턴스를 반환한다.

지원 제공자:
- OpenAI  : gpt-*, o1-*, o3-*
- Anthropic: claude-*
- Google  : gemini-*
"""

from langchain_core.language_models import BaseChatModel

# (model_name, temperature) 키로 LLM 인스턴스를 캐싱한다.
_cache: dict[tuple, BaseChatModel] = {}


def get_llm(model_name: str, temperature: float = 0, **kwargs) -> BaseChatModel:
    """
    캐시된 LLM 인스턴스 반환 (없으면 생성 후 캐싱)

    동일한 (model_name, temperature, kwargs) 조합은 항상 같은 인스턴스를 반환한다.

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
    if not model_name:
        raise ValueError(
            "model_name이 비어있습니다. "
            "config['configurable']['model'] 또는 환경변수 CHATGPT_MODEL_NAME을 설정하세요."
        )
    key = (model_name, temperature, tuple(sorted(kwargs.items())))
    if key not in _cache:
        _cache[key] = create_llm(model_name, temperature, **kwargs)
    return _cache[key]


def create_llm(model_name: str, temperature: float = 0, **kwargs) -> BaseChatModel:
    """
    모델명으로 LLM 인스턴스 생성 (캐싱 없음 — 직접 호출보다 get_llm() 사용 권장)

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
