"""
Upload Job Store — 파일 업로드 백그라운드 처리를 위한 인메모리 Job 관리.
Job은 생성 후 upload_job_ttl_seconds(기본 1시간) 경과 시 cleanup_expired_jobs()로 제거된다.
"""

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

EVENT_BUFFER_SIZE = 200


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass(eq=False)
class UploadJob:
    job_id: str
    job_type: str  # "persona" | "product"
    creator_user_id: str
    status: JobStatus
    total: int
    events: deque[dict[str, Any]]
    evicted_count: int
    condition: asyncio.Condition
    created_at: datetime
    updated_at: datetime


_store: dict[str, UploadJob] = {}


def create_job(job_type: str, total: int, creator_user_id: str) -> UploadJob:
    job = UploadJob(
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        creator_user_id=creator_user_id,
        status=JobStatus.PENDING,
        total=total,
        events=deque(maxlen=EVENT_BUFFER_SIZE),
        evicted_count=0,
        condition=asyncio.Condition(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    _store[job.job_id] = job
    return job


def get_job(job_id: str) -> UploadJob | None:
    return _store.get(job_id)


async def append_event(job: UploadJob, event: dict[str, Any]) -> None:
    """이벤트를 replay 버퍼에 추가하고 대기 중인 SSE 연결을 모두 깨운다."""
    async with job.condition:
        if len(job.events) == job.events.maxlen:
            job.evicted_count += 1
        job.events.append(event)
        job.updated_at = datetime.now(timezone.utc)
        if event.get("type") in ("done", "error"):
            job.status = JobStatus.DONE if event["type"] == "done" else JobStatus.ERROR
        job.condition.notify_all()


async def cleanup_expired_jobs(ttl_seconds: int) -> int:
    """TTL이 지난 Job을 제거한다. 제거된 Job 수를 반환한다."""
    now = datetime.now(timezone.utc)
    expired = [
        jid for jid, job in _store.items()
        if (now - job.updated_at).total_seconds() > ttl_seconds
    ]
    for jid in expired:
        del _store[jid]
    return len(expired)
