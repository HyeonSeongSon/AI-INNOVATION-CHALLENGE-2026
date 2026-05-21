"""
AuthProvider 계층 — API Key (레거시) / JWT (현재) 전환 가능 구조.

전환 방법:
    .env에서 AUTH_MODE=jwt, JWT_SECRET=<secret> 설정 → get_auth_provider()가 JWTAuthProvider 반환.
    marketing_api.py, deps.py 코드 변경 불필요.
"""

import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException, Request

from ..config.settings import settings


@dataclass
class UserContext:
    user_id: str
    auth_method: Literal["api_key", "jwt"]
    role: str = field(default="user")   # "admin" | "user"
    email: str = field(default="")


class AuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, request: Request) -> UserContext: ...


class APIKeyAuthProvider(AuthProvider):
    """X-API-Key 헤더 검증 후 X-User-Id를 신뢰."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def authenticate(self, request: Request) -> UserContext:
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key or not hmac.compare_digest(provided_key, self._api_key):
            raise HTTPException(status_code=401, detail="유효하지 않은 API Key입니다.")

        user_id = request.headers.get("X-User-Id", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="X-User-Id 헤더가 필요합니다.")

        return UserContext(user_id=user_id, auth_method="api_key")


class JWTAuthProvider(AuthProvider):
    """HttpOnly Cookie에서 Access Token(JWT) 추출 → 검증 → UserContext 반환."""

    def __init__(self, jwt_secret: str, algorithm: str = "HS256") -> None:
        self._jwt_secret = jwt_secret
        self._algorithm = algorithm

    async def authenticate(self, request: Request) -> UserContext:
        from jose import JWTError, jwt as jose_jwt

        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(
                status_code=401,
                detail="인증이 필요합니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jose_jwt.decode(token, self._jwt_secret, algorithms=[self._algorithm])
        except JWTError:
            raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")

        user_id: str = payload.get("sub", "")
        role: str = payload.get("role", "user")
        email: str = payload.get("email", "")
        token_type: str = payload.get("type", "")

        if not user_id or token_type != "access":
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        return UserContext(user_id=user_id, auth_method="jwt", role=role, email=email)


def get_auth_provider() -> AuthProvider:
    """settings.auth_mode에 따라 AuthProvider 구현체 반환."""
    if settings.auth_mode == "jwt":
        return JWTAuthProvider(settings.jwt_secret, settings.jwt_algorithm)
    return APIKeyAuthProvider(settings.service_api_key)
