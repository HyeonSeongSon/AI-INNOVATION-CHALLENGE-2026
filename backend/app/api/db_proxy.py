"""
DB Proxy Router — BFF(Backend for Frontend) 패턴.
프론트엔드 요청을 JWT 인증 후 내부 database:8020 서비스로 투명하게 전달한다.
프론트엔드는 이 라우터를 통해 데이터에 접근하며, database 서비스 포트는 외부에 노출하지 않는다.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config.settings import settings
from ..core.auth import UserContext
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["DB Proxy"])


def get_internal_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.internal_client


async def _proxy(client: httpx.AsyncClient, method: str, path: str, request: Request, extra_headers: dict | None = None) -> Response:
    body = await request.body()
    params = dict(request.query_params)
    content_type = request.headers.get("Content-Type", "application/json")
    headers = {"Content-Type": content_type, **(extra_headers or {})}

    try:
        upstream = await client.request(
            method=method,
            url=path,
            content=body,
            params=params,
            headers=headers,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Database service timeout")

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


# ── Conversations ─────────────────────────────────────────────────────────────

@router.post("/conversations", status_code=201)
async def proxy_conversations_create(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    try:
        body_data = await request.json()
    except Exception:
        body_data = {}
    body_data["user_id"] = user.user_id
    try:
        upstream = await client.post("/api/conversations", json=body_data)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Database service timeout")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.get("/conversations")
async def proxy_conversations_list(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "GET", "/api/conversations", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.get("/conversations/{conv_id}")
async def proxy_conversations_get(
    conv_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "GET", f"/api/conversations/{conv_id}", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.put("/conversations/{conv_id}/messages")
async def proxy_conversations_update(
    conv_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "PUT", f"/api/conversations/{conv_id}/messages", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.delete("/conversations/{conv_id}")
async def proxy_conversations_delete(
    conv_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "DELETE", f"/api/conversations/{conv_id}", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


# ── Personas ──────────────────────────────────────────────────────────────────

@router.post("/personas/list")
async def proxy_personas_list(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    try:
        body_data = await request.json()
    except Exception:
        body_data = {}
    body_data["user_id"] = user.user_id
    body_data["role"] = user.role
    try:
        upstream = await client.post("/api/personas/list", json=body_data)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Database service timeout")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.delete("/personas")
async def proxy_personas_bulk_delete(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "DELETE", "/api/personas", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


# ── Product Search Queries ─────────────────────────────────────────────────────

@router.post("/product-search-queries/get")
async def proxy_product_search_queries_get(
    request: Request,
    _: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(client, "POST", "/api/product-search-queries/get", request)


# ── Generated Messages ────────────────────────────────────────────────────────

@router.get("/generated-messages/filter-options")
async def proxy_generated_messages_filter_options(
    request: Request,
    _: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(client, "GET", "/api/generated-messages/filter-options", request)


@router.get("/generated-messages")
async def proxy_generated_messages_list(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "GET", "/api/generated-messages", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.get("/generated-messages/count")
async def proxy_generated_messages_count(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "GET", "/api/generated-messages/count", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.get("/generated-messages/latest")
async def proxy_generated_messages_latest(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "GET", "/api/generated-messages/latest", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


@router.delete("/generated-messages")
async def proxy_generated_messages_delete(
    request: Request,
    user: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(
        client, "DELETE", "/api/generated-messages", request,
        {"X-User-Id": user.user_id, "X-User-Role": user.role},
    )


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
async def proxy_products_list(
    request: Request,
    _: UserContext = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_internal_client),
):
    return await _proxy(client, "GET", "/api/products", request)
