from sqlalchemy.orm import Session
from sqlalchemy import text


def resolve_role(db: Session, user_id: str | None) -> str:
    """user_id로 users 테이블에서 실제 role을 조회한다.
    user_id가 없거나 users 테이블에 없으면 'user' 반환."""
    if not user_id:
        return "user"
    row = db.execute(
        text("SELECT role FROM users WHERE id::text = :uid"),
        {"uid": user_id}
    ).fetchone()
    return row[0] if row else "user"
