"""FastAPI 공용 의존성."""

from fastapi import Depends, HTTPException, Request

from ..core.auth import AuthProvider, UserContext, get_auth_provider


async def get_current_user(
    request: Request,
    provider: AuthProvider = Depends(get_auth_provider),
) -> UserContext:
    return await provider.authenticate(request)


async def require_admin(
    current_user: UserContext = Depends(get_current_user),
) -> UserContext:
    """admin 역할만 접근 허용. 그 외 403 반환."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return current_user
