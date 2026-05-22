from fastapi import Request

from ..config.settings import settings


def get_client_ip(request: Request) -> str:
    """
    실제 클라이언트 IP 반환.
    request.client.host가 trusted_proxy_ips에 속하면
    X-Forwarded-For의 오른쪽에서 trusted_proxy_count번째 IP를 사용.
    클라이언트가 헤더를 조작해도 trusted proxy가 append한 항목만 신뢰하므로 스푸핑 불가.
    """
    client_host = request.client.host if request.client else None
    if client_host and client_host in settings.trusted_proxy_ips:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        if len(ips) >= settings.trusted_proxy_count:
            return ips[-settings.trusted_proxy_count]
    return client_host or "unknown"
