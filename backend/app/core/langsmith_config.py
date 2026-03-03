"""
LangSmith 트레이싱 설정 모듈.

LangSmith 트레이싱은 환경 변수로 제어됩니다:
- LANGCHAIN_TRACING_V2=true          -> 트레이싱 활성화
- LANGCHAIN_API_KEY=ls__...          -> LangSmith API 키
- LANGCHAIN_PROJECT=crm-agent-prod   -> 대시보드의 프로젝트 이름

위 환경 변수가 설정되면 모든 LangChain/LangGraph 작업이
자동으로 추적됩니다 (ChatOpenAI, workflow.invoke 등).

이 모듈이 제공하는 기능:
1. 환경 변수가 올바르게 설정되었는지 검증
2. LangChain 외부 함수(API 호출, 검색 등)를 위한 @traced 데코레이터
"""

import os
import asyncio
import functools
from typing import Any, Callable, Optional

from .logging import get_logger

logger = get_logger("langsmith")


def configure_langsmith() -> bool:
    """
    LangSmith 설정 상태를 검증하고 로깅합니다.
    트레이싱이 활성화되면 True, 아니면 False를 반환합니다.

    애플리케이션 시작 시 한 번만 호출하세요.
    """
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key = os.getenv("LANGCHAIN_API_KEY")
    project = os.getenv("LANGCHAIN_PROJECT", "default")

    if tracing_enabled:
        if not api_key:
            logger.warning(
                "langsmith_misconfigured",
                detail="LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY is not set",
            )
            return False

        logger.info(
            "langsmith_enabled",
            project=project,
            endpoint=os.getenv(
                "LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"
            ),
        )
        return True
    else:
        logger.info(
            "langsmith_disabled",
            detail="Set LANGCHAIN_TRACING_V2=true to enable",
        )
        return False


def traced(
    name: Optional[str] = None,
    run_type: str = "chain",
    metadata: Optional[dict] = None,
):
    """
    LangChain 외부 함수를 LangSmith에서 추적하기 위한 데코레이터.

    외부 API 호출, 데이터 처리 등에 사용합니다.

    Args:
        name: LangSmith에서의 실행 이름 (기본값: 함수 이름)
        run_type: "chain", "tool", "retriever", 또는 "llm"
        metadata: 추가 메타데이터 딕셔너리

    사용 예시:
        @traced(name="fetch_persona", run_type="tool")
        def get_persona_info(self, persona_id: str) -> dict:
            ...

    langsmith가 설치되지 않았거나 트레이싱이 비활성화된 경우,
    데코레이터는 아무 동작 없이 원본 함수를 그대로 반환합니다.
    """

    def decorator(func: Callable) -> Callable:
        try:
            from langsmith import traceable

            ls_available = True
        except ImportError:
            ls_available = False

        if ls_available and os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
            trace_name = name or func.__name__
            trace_metadata = metadata or {}

            if asyncio.iscoroutinefunction(func):
                @traceable(
                    name=trace_name, run_type=run_type, metadata=trace_metadata
                )
                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await func(*args, **kwargs)

                return async_wrapper
            else:
                @traceable(
                    name=trace_name, run_type=run_type, metadata=trace_metadata
                )
                @functools.wraps(func)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    return func(*args, **kwargs)

                return wrapper
        else:
            return func

    return decorator
