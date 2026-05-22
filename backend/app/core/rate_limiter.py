import asyncio
import time
from collections import deque


class InMemoryRateLimiter:
    """슬라이딩 윈도우 방식 rate limiter. 단일 asyncio 이벤트 루프 전용."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._store: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> tuple[bool, int]:
        """(허용 여부, Retry-After 초) 반환. 허용 시 retry_after=0."""
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window

            window = self._store.setdefault(key, deque())

            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= self._max:
                retry_after = int(window[0] - cutoff) + 1
                return False, retry_after

            window.append(now)
            return True, 0
