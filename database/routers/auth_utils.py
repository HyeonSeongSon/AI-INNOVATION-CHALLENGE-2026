import os

from fastapi import HTTPException, Request
from jose import JWTError, jwt as jose_jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

_INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")


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


def _decode_assertion(token: str) -> dict:
    return jose_jwt.decode(token, _INTERNAL_TOKEN, algorithms=["HS256"])


def get_request_user_id(request: Request) -> str:
    """FastAPI Depends: X-User-Assertion JWT에서 검증된 user_id 반환."""
    token = request.headers.get("X-User-Assertion", "")
    if not token:
        raise HTTPException(status_code=401, detail="User context missing")
    try:
        return _decode_assertion(token)["user_id"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid user assertion")


def get_user_id_from_request(request: Request | None) -> str | None:
    """raw_request 패턴용: X-User-Assertion에서 user_id 반환. 없거나 invalid면 None."""
    if not request:
        return None
    token = request.headers.get("X-User-Assertion", "")
    if not token:
        return None
    try:
        return _decode_assertion(token)["user_id"]
    except (JWTError, KeyError):
        return None
