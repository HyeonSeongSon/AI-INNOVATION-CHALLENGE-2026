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
from .deps import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["CRM Proxy"])

_crm_client: httpx.AsyncClient | None = None


def get_crm_client() -> httpx.AsyncClient:
    global _crm_client
    if _crm_client is None or _crm_client.is_closed:
        _crm_client = httpx.AsyncClient(
            base_url=settings.crm_service_url,
            headers={"X-Internal-Token": settings.internal_token},
            timeout=httpx.Timeout(settings.http_timeout_long),
        )
    return _crm_client


async def close_crm_client() -> None:
    global _crm_client
    if _crm_client is not None and not _crm_client.is_closed:
        await _crm_client.aclose()


async def _proxy(
    method: str,
    path: str,
    request: Request,
    extra_headers: dict | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> Response:
    client = get_crm_client()
    body = await request.body()
    params = dict(request.query_params)
    content_type = request.headers.get("Content-Type", "application/json")
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
    method: str,
    path: str,
    request: Request,
    extra_headers: dict | None = None,
) -> StreamingResponse:
    """SSE 스트리밍 프록시. read timeout=None으로 처리 완료까지 연결 유지."""
    client = get_crm_client()
    body = await request.body()
    params = dict(request.query_params)
    content_type = request.headers.get("Content-Type", "")
    headers = {"Content-Type": content_type, **(extra_headers or {})}

    async def generate():
        try:
            async with client.stream(
                method=method,
                url=path,
                content=body,
                params=params,
                headers=headers,
                timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=5.0),
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.ConnectError:
            yield b'data: {"type":"error","detail":"CRM service unavailable"}\n\n'
        except httpx.TimeoutException:
            yield b'data: {"type":"error","detail":"CRM service timeout"}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────
# Marketing
# ──────────────────────────────────────────────────────

@router.post("/marketing/chat/v2")
async def proxy_chat_v2(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    return await _proxy(
        "POST", "/api/marketing/chat/v2", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
        timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=5.0),
    )


@router.get("/marketing/health")
async def proxy_marketing_health(request: Request):
    return await _proxy("GET", "/api/marketing/health", request)


# ──────────────────────────────────────────────────────
# Pipeline — Products
# ──────────────────────────────────────────────────────

@router.post("/pipeline/products/register")
async def proxy_products_register(
    request: Request,
    user: UserContext = Depends(require_admin),
):
    return await _proxy_stream(
        "POST", "/api/pipeline/products/register", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


# ──────────────────────────────────────────────────────
# Pipeline — Personas
# ──────────────────────────────────────────────────────

@router.post("/pipeline/personas/create-from-text")
async def proxy_personas_create_from_text(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    return await _proxy(
        "POST", "/api/pipeline/personas/create-from-text", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.post("/pipeline/personas/create-from-file")
async def proxy_personas_create_from_file(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    return await _proxy_stream(
        "POST", "/api/pipeline/personas/create-from-file", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.post("/pipeline/personas/create-from-file/upload")
async def proxy_personas_upload(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    timeout = httpx.Timeout(
        connect=10.0,
        read=settings.upload_file_read_timeout + settings.upload_file_parse_timeout + 10.0,
        write=settings.http_timeout_upload,
        pool=5.0,
    )
    return await _proxy(
        "POST", "/api/pipeline/personas/create-from-file/upload", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
        timeout,
    )


@router.get("/pipeline/personas/jobs/{job_id}/stream")
async def proxy_personas_stream(
    job_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    return await _proxy_stream(
        "GET", f"/api/pipeline/personas/jobs/{job_id}/stream", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.post("/pipeline/products/register/upload")
async def proxy_products_upload(
    request: Request,
    user: UserContext = Depends(require_admin),
):
    timeout = httpx.Timeout(
        connect=10.0,
        read=settings.upload_file_read_timeout + settings.upload_file_parse_timeout + 10.0,
        write=settings.http_timeout_upload,
        pool=5.0,
    )
    return await _proxy(
        "POST", "/api/pipeline/products/register/upload", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
        timeout,
    )


@router.get("/pipeline/products/jobs/{job_id}/stream")
async def proxy_products_stream(
    job_id: str,
    request: Request,
    user: UserContext = Depends(require_admin),
):
    return await _proxy_stream(
        "GET", f"/api/pipeline/products/jobs/{job_id}/stream", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )
