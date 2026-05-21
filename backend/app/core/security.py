"""
보안 유틸리티: JWT 생성, bcrypt 비밀번호 해싱, Refresh Token 생성/해싱.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt as jose_jwt
from passlib.context import CryptContext

from ..config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ──────────────────────────────────────────────────────
# 비밀번호
# ──────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ──────────────────────────────────────────────────────
# Access Token (JWT, HS256)
# ──────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ──────────────────────────────────────────────────────
# Refresh Token (opaque, SHA-256 해시 저장)
# ──────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """암호학적으로 안전한 128자 hex 토큰."""
    return secrets.token_hex(64)


def hash_token(raw_token: str) -> str:
    """SHA-256 해시 → DB 저장용. raw 토큰은 DB에 저장하지 않는다."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def get_refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
