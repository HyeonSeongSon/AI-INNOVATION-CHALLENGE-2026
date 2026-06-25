import asyncio
import random
from typing import Any
from langchain_core.runnables import Runnable
from ..config.settings import settings


async def ainvoke_with_timeout(runnable: Runnable, input: Any, timeout: float | None = None) -> Any:
    t = timeout if timeout is not None else settings.llm_call_timeout
    return await asyncio.wait_for(runnable.ainvoke(input), timeout=t)


# provider 무관 재시도 판별 — type(e).__name__만 본다(openai.RateLimitError 등 provider
# 전용 클래스를 import하면 llm이 Anthropic/Gemini일 때 잡지 못한다).
_RETRYABLE_LLM_ERROR_NAMES = frozenset({
    "RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError",
    "TimeoutError",
})

_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_semaphore(key: str, limit: int) -> asyncio.Semaphore:
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(limit)
    return _semaphores[key]


async def ainvoke_with_retry(
    runnable: Runnable,
    input: Any,
    *,
    semaphore_key: str,
    max_concurrency: int,
    max_retries: int,
    backoff_base: float,
    logger,
    retry_event: str,
    timeout: float | None = None,
) -> Any:
    """provider 무관 재시도 + 호출 지점별 전용 동시성 제한 + Full Jitter 백오프.

    100개 동시 세션이 같은 LLM 호출 지점에 비슷한 시점에 수렴해 OpenAI 응답이
    느려지면, 무방비 호출은 타임아웃이 한꺼번에 터진다(38차 부하테스트에서
    supervisor_agent 최종 응답 호출 42건 발생). semaphore_key별로 세마포어를
    lazy 생성해 호출 지점마다 독립적인 동시성 한도를 두고, 재시도 대기는 고정
    백오프 대신 0~상한 사이 무작위(Full Jitter)로 흩어 재시도 자체가 다시
    부하를 만드는 "재시도 동기화"를 막는다.
    """
    async with _get_semaphore(semaphore_key, max_concurrency):
        for attempt in range(1, max_retries + 1):
            try:
                return await ainvoke_with_timeout(runnable, input, timeout=timeout)
            except Exception as e:
                is_retryable = type(e).__name__ in _RETRYABLE_LLM_ERROR_NAMES
                if is_retryable and attempt < max_retries:
                    base = backoff_base * (2 ** (attempt - 1))
                    logger.warning(retry_event, error_type=type(e).__name__, attempt=attempt)
                    await asyncio.sleep(random.uniform(0, base))
                    continue
                raise
