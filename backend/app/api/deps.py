"""FastAPI 공용 의존성."""

from fastapi import Depends, Request

from ..core.auth import AuthProvider, UserContext, get_auth_provider


async def get_current_user(
    request: Request,
    provider: AuthProvider = Depends(get_auth_provider),
) -> UserContext:
    return await provider.authenticate(request)
