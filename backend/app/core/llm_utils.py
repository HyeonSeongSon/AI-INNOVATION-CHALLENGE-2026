import asyncio
from typing import Any
from langchain_core.runnables import Runnable
from ..config.settings import settings


async def ainvoke_with_timeout(runnable: Runnable, input: Any, timeout: float | None = None) -> Any:
    t = timeout if timeout is not None else settings.llm_call_timeout
    return await asyncio.wait_for(runnable.ainvoke(input), timeout=t)
