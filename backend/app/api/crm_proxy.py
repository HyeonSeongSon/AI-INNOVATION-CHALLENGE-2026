"""
CRM Proxy Router — BFF 패턴.
프론트엔드 요청을 JWT 인증 후 내부 crm-service:8006으로 전달한다.
SSE 스트리밍 엔드포인트는 청크를 그대로 릴레이한다.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..config.settings import settings
from ..core.auth import UserContext
from ..core.auth_utils import create_user_assertion
from ..core.rate_limiter import PostgresRateLimiter
from .deps import get_chat_limiter, get_current_user, get_persona_delete_limiter, get_persona_text_limiter, get_persona_upload_limiter, get_product_upload_limiter, require_admin

router = APIRouter(prefix="/api", tags=["CRM Proxy"])

_ALLOWED_CONTENT_TYPES = ("application/json", "multipart/form-data", "application/octet-stream")


def get_crm_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.crm_client


async def _proxy(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    request: Request,
    extra_headers: dict | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> Response:
    body = await request.body()
    params = dict(request.query_params)
    content_type = request.headers.get("Content-Type", "application/json")
    if not any(content_type.startswith(ct) for ct in _ALLOWED_CONTENT_TYPES):
        raise HTTPException(status_code=415, detail="Unsupported Media Type")
    headers = {"Content-Type": content_type, **(extra_headers or {})}
    if isinstance(timeout, (int, float)):
        request_timeout = httpx.Timeout(timeout)
    else:
        request_timeout = timeout  # httpx.Timeout 객체 또는 None(클라이언트 기본값)

    try:
        upstream = await client.request(
            method=method,
            url=path,
            content=body,
            params=params,
            headers=headers,
            timeout=request_timeout,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="CRM service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CRM service timeout")

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


async def _proxy_stream(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    request: Request,
    extra_headers: dict | None = None,
) -> StreamingResponse:
    """SSE 스트리밍 프록시. read timeout=None으로 처리 완료까지 연결 유지."""
    body = await request.body()
    params = dict(request.query_params)
    headers = {"Content-Type": "application/json", **(extra_headers or {})}

    async def generate():
        try:
            async with client.stream(
                method=method,
                url=path,
                content=body,
                params=params,
                headers=headers,
                timeout=httpx.Timeout(connect=settings.http_timeout_stream_connect, read=None, write=None, pool=settings.http_timeout_stream_pool),
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.TimeoutException:
            yield b'data: {"type":"error","detail":"CRM service timeout"}\n\n'
        except httpx.RequestError:
            yield b'data: {"type":"error","detail":"CRM service unavailable"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────────────
# Marketing
# ──────────────────────────────────────────────────────

@router.post("/marketing/chat/v2")
async def proxy_chat_v2(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
    limiter: PostgresRateLimiter = Depends(get_chat_limiter),
):
    allowed, retry_after = await limiter.is_allowed(user.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    return await _proxy(
        client, "POST", "/api/marketing/chat/v2", request,
        {"X-User-Assertion": create_user_assertion(user)},
        timeout=httpx.Timeout(connect=settings.http_timeout_stream_connect, read=None, write=None, pool=settings.http_timeout_stream_pool),
    )


@router.post("/marketing/chat/v2/stream")
async def proxy_chat_v2_stream(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
    limiter: PostgresRateLimiter = Depends(get_chat_limiter),
):
    allowed, retry_after = await limiter.is_allowed(user.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    return await _proxy_stream(
        client, "POST", "/api/marketing/chat/v2/stream", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )


@router.get("/marketing/health")
async def proxy_marketing_health(
    request: Request,
    client: httpx.AsyncClient = Depends(get_crm_client),
):
    return await _proxy(client, "GET", "/api/marketing/health", request)


# ──────────────────────────────────────────────────────
# Pipeline — Products
# ──────────────────────────────────────────────────────

@router.post("/pipeline/products/register")
async def proxy_products_register(
    request: Request,
    user: UserContext = Depends(require_admin),
    client: httpx.AsyncClient = Depends(get_crm_client),
):
    return await _proxy_stream(
        client, "POST", "/api/pipeline/products/register", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )


# ──────────────────────────────────────────────────────
# Pipeline — Personas
# ──────────────────────────────────────────────────────

@router.post("/pipeline/personas/create-from-text")
async def proxy_personas_create_from_text(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
    limiter: PostgresRateLimiter = Depends(get_persona_text_limiter),
):
    allowed, retry_after = await limiter.is_allowed(user.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    return await _proxy(
        client, "POST", "/api/pipeline/personas/create-from-text", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )


@router.post("/pipeline/personas/create-from-file")
async def proxy_personas_create_from_file(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
):
    return await _proxy_stream(
        client, "POST", "/api/pipeline/personas/create-from-file", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )


@router.post("/pipeline/personas/create-from-file/upload")
async def proxy_personas_upload(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
    limiter: PostgresRateLimiter = Depends(get_persona_upload_limiter),
):
    allowed, retry_after = await limiter.is_allowed(user.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    timeout = httpx.Timeout(
        connect=settings.http_timeout_stream_connect,
        read=settings.upload_file_read_timeout + settings.upload_file_parse_timeout + 10.0,
        write=settings.http_timeout_upload,
        pool=settings.http_timeout_stream_pool,
    )
    return await _proxy(
        client, "POST", "/api/pipeline/personas/create-from-file/upload", request,
        {"X-User-Assertion": create_user_assertion(user)},
        timeout,
    )


@router.get("/pipeline/personas/jobs/{job_id}/stream")
async def proxy_personas_stream(
    job_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_crm_client),
):
    return await _proxy_stream(
        client, "GET", f"/api/pipeline/personas/jobs/{job_id}/stream", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )


@router.post("/pipeline/products/register/upload")
async def proxy_products_upload(
    request: Request,
    user: UserContext = Depends(require_admin),
    client: httpx.AsyncClient = Depends(get_crm_client),
    limiter: PostgresRateLimiter = Depends(get_product_upload_limiter),
):
    allowed, retry_after = await limiter.is_allowed(user.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )
    timeout = httpx.Timeout(
        connect=settings.http_timeout_stream_connect,
        read=settings.upload_file_read_timeout + settings.upload_file_parse_timeout + 10.0,
        write=settings.http_timeout_upload,
        pool=settings.http_timeout_stream_pool,
    )
    return await _proxy(
        client, "POST", "/api/pipeline/products/register/upload", request,
        {"X-User-Assertion": create_user_assertion(user)},
        timeout,
    )


@router.get("/pipeline/products/jobs/{job_id}/stream")
async def proxy_products_stream(
    job_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
    client: httpx.AsyncClient = Depends(get_crm_client),
):
    return await _proxy_stream(
        client, "GET", f"/api/pipeline/products/jobs/{job_id}/stream", request,
        {"X-User-Assertion": create_user_assertion(user)},
    )
