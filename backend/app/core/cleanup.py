import asyncio
from datetime import timedelta

from sqlalchemy import text

from app.config.settings import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger

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


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(settings.cleanup_interval_seconds)
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
