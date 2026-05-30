"""
내부 사용자 어설션 JWT 유틸리티.
API Gateway가 인증 후 INTERNAL_TOKEN으로 서명한 단명 JWT를 생성/검증한다.
다운스트림 서비스는 raw X-User-Id 헤더 대신 이 JWT를 신뢰한다.
"""

import time

from jose import jwt as jose_jwt

from ..config.settings import settings
from .auth import UserContext


def create_user_assertion(user: UserContext) -> str:
    """인증된 UserContext를 서명된 JWT로 직렬화한다. 다운스트림 요청 헤더에 첨부."""
    payload = {
        "user_id": user.user_id,
        "role": user.role,
        "email": user.email,
        "auth_method": user.auth_method,
        "exp": int(time.time()) + settings.user_assertion_expire_seconds,
    }
    return jose_jwt.encode(payload, settings.internal_token, algorithm="HS256")


def verify_user_assertion(token: str) -> UserContext:
    """X-User-Assertion JWT 검증 후 UserContext 반환. 서명 오류/만료 시 JWTError 발생."""
    payload = jose_jwt.decode(token, settings.internal_token, algorithms=["HS256"])
    return UserContext(
        user_id=payload["user_id"],
        role=payload.get("role", "user"),
        email=payload.get("email", ""),
        auth_method=payload.get("auth_method", "jwt"),
    )
