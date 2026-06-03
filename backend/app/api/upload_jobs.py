"""
Upload Job Store — PostgreSQL 기반 파일 업로드 백그라운드 처리 Job 관리.
단일 프로세스뿐 아니라 다중 워커(uvicorn --workers N) 환경을 지원한다.

Job 상태 전이: pending → running → done | error

TTL:
  done/error 상태: upload_job_done_ttl_seconds(기본 5분) 후 cleanup
  그 외:           upload_job_ttl_seconds(기본 1시간) 후 cleanup
"""

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class UploadJob:
    job_id: str
    job_type: str
    creator_user_id: str
    status: JobStatus
    total: int


def set_pool(pool: AsyncConnectionPool) -> None:
    global _pool
    _pool = pool


async def create_job(job_type: str, total: int, creator_user_id: str) -> UploadJob | None:
    from app.config.settings import settings

    assert _pool is not None, "upload_jobs pool not initialized"

    async with _pool.connection() as conn:
        row = await conn.execute(
            """
            SELECT COUNT(*) FROM upload_jobs
            WHERE creator_user_id = %s AND status IN ('pending', 'running')
            """,
            (creator_user_id,),
        )
        (active,) = await row.fetchone()
        if active >= settings.max_active_jobs_per_user:
            return None

        job_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO upload_jobs (job_id, job_type, creator_user_id, status, total)
            VALUES (%s, %s, %s, 'pending', %s)
            """,
            (job_id, job_type, creator_user_id, total),
        )

    return UploadJob(
        job_id=job_id,
        job_type=job_type,
        creator_user_id=creator_user_id,
        status=JobStatus.PENDING,
        total=total,
    )


async def get_job(job_id: str) -> UploadJob | None:
    assert _pool is not None, "upload_jobs pool not initialized"

    async with _pool.connection() as conn:
        row = await conn.execute(
            "SELECT job_id, job_type, creator_user_id, status, total FROM upload_jobs WHERE job_id = %s",
            (job_id,),
        )
        record = await row.fetchone()

    if record is None:
        return None
    return UploadJob(
        job_id=record[0],
        job_type=record[1],
        creator_user_id=record[2],
        status=JobStatus(record[3]),
        total=record[4],
    )


async def append_event(job: UploadJob, event: dict[str, Any]) -> None:
    assert _pool is not None, "upload_jobs pool not initialized"

    event_type = event.get("type")
    async with _pool.connection() as conn:
        await conn.execute(
            "INSERT INTO upload_job_events (job_id, event_data) VALUES (%s, %s)",
            (job.job_id, event),
        )
        if event_type in ("done", "error"):
            new_status = "done" if event_type == "done" else "error"
            await conn.execute(
                "UPDATE upload_jobs SET status = %s, updated_at = NOW() WHERE job_id = %s",
                (new_status, job.job_id),
            )
            job.status = JobStatus(new_status)
        else:
            await conn.execute(
                "UPDATE upload_jobs SET status = 'running', updated_at = NOW() WHERE job_id = %s",
                (job.job_id,),
            )


async def get_events_after(job_id: str, after_id: int) -> list[tuple[int, dict[str, Any]]]:
    """event id > after_id 인 이벤트를 (id, event_data) 순서대로 반환한다."""
    assert _pool is not None, "upload_jobs pool not initialized"

    async with _pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT id, event_data FROM upload_job_events
            WHERE job_id = %s AND id > %s ORDER BY id
            """,
            (job_id, after_id),
        )
        records = await rows.fetchall()

    return [(r[0], r[1]) for r in records]


async def cleanup_expired_jobs(ttl_seconds: int, done_ttl_seconds: int) -> int:
    assert _pool is not None, "upload_jobs pool not initialized"

    async with _pool.connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM upload_jobs
            WHERE (status IN ('done', 'error')
                   AND updated_at < NOW() - make_interval(secs => %s))
               OR (status NOT IN ('done', 'error')
                   AND updated_at < NOW() - make_interval(secs => %s))
            """,
            (done_ttl_seconds, ttl_seconds),
        )
        return result.rowcount
