"""
AuthProvider 계층 — API Key (현재) / JWT (추후) 전환 가능 구조.

전환 방법:
    .env에서 AUTH_MODE=jwt, JWT_SECRET=<secret> 설정 → get_auth_provider()가 JWTAuthProvider 반환.
    marketing_api.py, deps.py 코드 변경 불필요.
"""

import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request

from ..config.settings import settings


@dataclass
class UserContext:
    user_id: str
    auth_method: Literal["api_key", "jwt"]


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
    """Bearer JWT 검증 → claims에서 user_id 추출. (로그인 시스템 도입 시 구현)"""

    def __init__(self, jwt_secret: str) -> None:
        self._jwt_secret = jwt_secret

    async def authenticate(self, request: Request) -> UserContext:
        # TODO: 로그인 시스템 도입 시 구현
        #   import jwt
        #   token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        #   payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
        #   return UserContext(user_id=payload["sub"], auth_method="jwt")
        raise NotImplementedError("JWT 인증은 아직 구현되지 않았습니다.")


def get_auth_provider() -> AuthProvider:
    """settings.auth_mode에 따라 AuthProvider 구현체 반환."""
    if settings.auth_mode == "jwt":
        return JWTAuthProvider(settings.jwt_secret)
    return APIKeyAuthProvider(settings.service_api_key)
