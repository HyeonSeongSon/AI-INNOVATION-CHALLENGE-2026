import asyncio
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

logger = get_logger("cleanup")


def _delete_expired_tokens() -> int:
    sql = text(
        "DELETE FROM refresh_tokens"
        " WHERE expires_at < NOW() - :grace_interval"
        " OR revoked = TRUE"
    )
    db = SessionLocal()
    try:
        result = db.execute(sql, {"grace_interval": timedelta(days=settings.cleanup_token_grace_days)})
        db.commit()
        return result.rowcount
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def evict_excess_tokens(db: Session, user_id: uuid.UUID, max_tokens: int) -> None:
    """활성 토큰이 max_tokens 이상이면 가장 오래된 것부터 삭제한다. commit은 호출자가 처리."""
    sql = text(
        "DELETE FROM refresh_tokens"
        " WHERE id IN ("
        "   SELECT id FROM refresh_tokens"
        "   WHERE user_id = :user_id AND revoked = FALSE AND expires_at > NOW()"
        "   ORDER BY created_at ASC"
        "   LIMIT GREATEST(0, ("
        "     SELECT COUNT(*) FROM refresh_tokens"
        "     WHERE user_id = :user_id AND revoked = FALSE AND expires_at > NOW()"
        "   ) - :keep)"
        " )"
    )
    db.execute(sql, {"user_id": user_id, "keep": max_tokens - 1})


def _delete_stale_rate_limits() -> int:
    sql = text(
        "DELETE FROM rate_limits WHERE window_start < NOW() - :threshold_interval"
    )
    db = SessionLocal()
    try:
        result = db.execute(sql, {"threshold_interval": timedelta(seconds=settings.lockout_per_ip_window_seconds * 2)})
        db.commit()
        return result.rowcount
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def cleanup_old_checkpoints(
    pool: "AsyncConnectionPool",
    retention_days: int,
    batch_size: int,
) -> int:
    """마지막 체크포인트가 retention_days보다 오래된 thread를 모두 삭제한다."""
    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT thread_id FROM checkpoints
            GROUP BY thread_id
            HAVING MAX(created_at) < NOW() - make_interval(days => %s)
            LIMIT %s
            """,
            [retention_days, batch_size],
        )
        thread_ids = [r[0] for r in await rows.fetchall()]

    if not thread_ids:
        return 0

    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = ANY(%s)", [thread_ids]
            )
            await conn.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = ANY(%s)", [thread_ids]
            )
            await conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = ANY(%s)", [thread_ids]
            )

    return len(thread_ids)


async def cleanup_loop() -> None:
    while True:
        try:
            tokens_deleted = await asyncio.to_thread(_delete_expired_tokens)
            rate_limits_deleted = await asyncio.to_thread(_delete_stale_rate_limits)
            logger.info(
                "db_cleanup_completed",
                tokens_deleted=tokens_deleted,
                rate_limits_deleted=rate_limits_deleted,
            )
        except Exception as e:
            logger.error("db_cleanup_failed", error_type=type(e).__name__, exc_info=True)
        await asyncio.sleep(settings.cleanup_interval_seconds)
