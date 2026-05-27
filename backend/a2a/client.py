import asyncio
import uuid
from typing import Optional

import httpx
from langchain_core.messages import BaseMessage

from .models import DataPart, Message, Task, TaskSendRequest
from .serialization import serialize_messages
from app.config.settings import settings
from app.core.logging import get_logger
from app.core.http_client_registry import register

_logger = get_logger("a2a_client")


class A2AClient:
    def __init__(self, base_url: str):
        # base_url: 에이전트 prefix까지 포함 (e.g. "http://localhost:8005/a2a/recommend-product")
        self.base_url = base_url.rstrip("/")
        self._http_client: Optional[httpx.AsyncClient] = None
        register(self)

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=settings.a2a_timeout,
                headers={"X-Internal-Token": settings.internal_token or ""},
            )
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def send_task(
        self,
        session_id: str,
        data: dict,
        timeout: httpx.Timeout | None = None,
    ) -> Task:
        serialized = {
            k: serialize_messages(v)
               if isinstance(v, list) and v and isinstance(v[0], BaseMessage)
               else v
            for k, v in data.items()
            if v is not None
        }
        req = TaskSendRequest(
            id=str(uuid.uuid4()),
            sessionId=session_id,
            message=Message(role="user", parts=[DataPart(data=serialized)]),
        )

        last_exc: Exception | None = None
        attempt_errors: list[str] = []

        for attempt in range(settings.a2a_max_retries):
            try:
                resp = await self.http_client.post(
                    f"{self.base_url}/tasks/send",
                    json=req.model_dump(),
                    timeout=timeout,
                )
                resp.raise_for_status()
                try:
                    return Task(**resp.json())
                except Exception as e:
                    _logger.error("a2a_response_parse_failed", error_type=type(e).__name__, exc_info=True)
                    raise ValueError("A2A 응답 파싱 실패") from None
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_exc = e
                error_type = type(e).__name__
                attempt_errors.append(f"attempt {attempt + 1}: {error_type}")
                _logger.warning(
                    "a2a_send_task_retry",
                    url=self.base_url,
                    attempt=attempt + 1,
                    max_retries=settings.a2a_max_retries,
                    error_type=error_type,
                )
                if attempt < settings.a2a_max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        _logger.error(
            "a2a_send_task_all_retries_exhausted",
            url=self.base_url,
            attempts=attempt_errors,
        )
        raise last_exc
