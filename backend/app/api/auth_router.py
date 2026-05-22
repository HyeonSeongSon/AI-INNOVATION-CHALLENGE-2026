"""
인증 API: 회원가입, 로그인, 토큰 갱신, 로그아웃, 내 정보 조회.
HttpOnly Cookie 방식 — 웹 프론트엔드 우선.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from ..config.settings import settings
from ..core.database import get_db
from ..core.logging import get_logger
from ..core.models import RefreshToken, User
from ..core.security import (
    create_access_token,
    generate_refresh_token,
    get_refresh_token_expiry,
    hash_password,
    hash_token,
    verify_password,
)
from .deps import get_current_user, get_login_limiter, get_register_limiter
from ..core.auth import UserContext
from ..core.rate_limiter import InMemoryRateLimiter

logger = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_SECURE = settings.environment == "production"
_COOKIE_SAMESITE = "lax"


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────
# Pydantic 모델
# ──────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 최소 8자 이상이어야 합니다.")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("admin", "user"):
            raise ValueError("role은 'admin' 또는 'user'만 허용됩니다.")
        return v


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime


# ──────────────────────────────────────────────────────
# 헬퍼: Cookie 설정 / 삭제
# ──────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        path="/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/auth")


# ──────────────────────────────────────────────────────
# POST /auth/register
# ──────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
    limiter: InMemoryRateLimiter = Depends(get_register_limiter),
):
    """회원가입. 이메일 중복 체크 후 bcrypt 해싱하여 저장."""
    ip = _get_client_ip(request)
    allowed, retry_after = await limiter.is_allowed(ip)
    if not allowed:
        logger.warning("rate_limit_exceeded", endpoint="register", client_ip=ip, retry_after=retry_after)
        raise HTTPException(
            status_code=429,
            detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user_registered", user_id=str(user.id), role=user.role)
    return UserResponse(id=str(user.id), email=user.email, role=user.role, created_at=user.created_at)


# ──────────────────────────────────────────────────────
# POST /auth/login
# ──────────────────────────────────────────────────────

@router.post("/login")
async def login(
    response: Response,
    request: Request,
    body: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    limiter: InMemoryRateLimiter = Depends(get_login_limiter),
):
    """
    로그인. 성공 시 HttpOnly Cookie에 access_token + refresh_token 세팅.
    Content-Type: application/x-www-form-urlencoded (username=email, password=password).
    """
    ip = _get_client_ip(request)
    allowed, retry_after = await limiter.is_allowed(ip)
    if not allowed:
        logger.warning("rate_limit_exceeded", endpoint="login", client_ip=ip, retry_after=retry_after)
        raise HTTPException(
            status_code=429,
            detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.email == body.username).first()

    # 타이밍 공격 방지: 사용자 없어도 dummy 해시 검증 수행
    if not user:
        verify_password(body.password, "$2b$12$dummyhashtopreventtimingattack00")
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    access_token = create_access_token(user_id=str(user.id), email=user.email, role=user.role)
    raw_refresh = generate_refresh_token()

    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=get_refresh_token_expiry(),
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(rt)
    db.commit()

    _set_auth_cookies(response, access_token, raw_refresh)

    logger.info("user_logged_in", user_id=str(user.id))
    return {"message": "로그인 성공", "user": {"id": str(user.id), "email": user.email, "role": user.role}}


# ──────────────────────────────────────────────────────
# POST /auth/refresh
# ──────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Refresh Token으로 새 Access Token + Refresh Token 발급 (Token Rotation).
    refresh_token Cookie는 Path=/auth로 제한되어 /auth/* 엔드포인트에만 전송된다.
    """
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Refresh Token이 없습니다.")

    rt = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == hash_token(raw_refresh),
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if not rt:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 Refresh Token입니다.")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    # Token Rotation: 기존 토큰 폐기
    rt.revoked = True

    new_access = create_access_token(user_id=str(user.id), email=user.email, role=user.role)
    new_raw_refresh = generate_refresh_token()

    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_raw_refresh),
        expires_at=get_refresh_token_expiry(),
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(new_rt)
    db.commit()

    _set_auth_cookies(response, new_access, new_raw_refresh)

    logger.info("token_refreshed", user_id=str(user.id))
    return {"message": "토큰 갱신 성공"}


# ──────────────────────────────────────────────────────
# POST /auth/logout
# ──────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    """로그아웃. Refresh Token DB에서 폐기 + 양쪽 Cookie 삭제."""
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        # Primary: 현재 기기의 refresh_token만 폐기. user_id 조건으로 IDOR 방지.
        rt = db.query(RefreshToken).filter(
            RefreshToken.token_hash == hash_token(raw_refresh),
            RefreshToken.user_id == current_user.user_id,
        ).first()
        if rt:
            rt.revoked = True
            db.commit()
    else:
        # Fallback: 쿠키가 없으면 해당 user의 모든 활성 refresh_token 일괄 폐기
        # (쿠키 만료 또는 탈취 후 쿠키 삭제 시나리오 대응 — AWS Cognito GlobalSignOut 패턴)
        db.query(RefreshToken).filter(
            RefreshToken.user_id == current_user.user_id,
            RefreshToken.revoked == False,
        ).update({"revoked": True})
        db.commit()

    _clear_auth_cookies(response)
    logger.info("user_logged_out", user_id=str(current_user.user_id))
    return {"message": "로그아웃 성공"}


# ──────────────────────────────────────────────────────
# GET /auth/me
# ──────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 로그인된 사용자 정보 조회."""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return UserResponse(id=str(user.id), email=user.email, role=user.role, created_at=user.created_at)
