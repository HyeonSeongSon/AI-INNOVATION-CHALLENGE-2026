import asyncio
import time
from collections import deque
from datetime import datetime, timezone, timedelta

from sqlalchemy.exc import IntegrityError

from app.core.models import RateLimitEntry


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


class PostgresRateLimiter:
    """슬라이딩 윈도우 카운터 rate limiter. PostgreSQL SELECT FOR UPDATE로 다중 worker/컨테이너 환경 지원.

    투-버킷 근사(Cloudflare 방식):
        effective_count = prev_count × (1 - elapsed/window) + curr_count
    윈도우 경계 버스트 없음. 최대 오차 ~10% (경계 직전에서 발생, 인증 용도에 적합).
    """

    def __init__(self, session_factory, max_requests: int, window_seconds: int) -> None:
        self._factory = session_factory
        self._max = max_requests
        self._window = window_seconds

    async def is_allowed(self, key: str) -> tuple[bool, int]:
        """(허용 여부, Retry-After 초) 반환. 허용 시 retry_after=0."""
        return await asyncio.to_thread(self._check, key)

    def _check(self, key: str) -> tuple[bool, int]:
        with self._factory() as db:
            entry: RateLimitEntry | None = (
                db.query(RateLimitEntry)
                .filter_by(key=key)
                .with_for_update()
                .first()
            )
            now = datetime.now(tz=timezone.utc)

            if entry is None:
                try:
                    db.add(RateLimitEntry(key=key, count=1, window_start=now, prev_count=0))
                    db.commit()
                    return True, 0
                except IntegrityError:
                    db.rollback()
                    return self._check(key)  # 동시 INSERT 경쟁 — 행이 이미 생성됨, 재시도

            elapsed = (now - entry.window_start).total_seconds()

            if elapsed >= 2 * self._window:
                # 데이터가 2 윈도우 이상 오래됨 → 이전 카운트 의미 없음, 완전 초기화
                entry.prev_count = 0
                entry.count = 1
                entry.window_start = now
                db.commit()
                return True, 0

            if elapsed >= self._window:
                # 윈도우 롤오버: 현재 버킷 → 이전 버킷, 새 버킷 초기화
                entry.prev_count = entry.count
                entry.count = 0
                elapsed = elapsed % self._window
                entry.window_start = now - timedelta(seconds=elapsed)

            # 이 요청 포함 projected effective count
            effective = entry.prev_count * (1.0 - elapsed / self._window) + entry.count + 1

            if effective > self._max:
                retry_after = int(self._window - elapsed) + 1
                return False, retry_after

            entry.count += 1
            db.commit()
            return True, 0
