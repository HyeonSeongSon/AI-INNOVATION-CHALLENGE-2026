import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config.settings import settings

_SKIP_PATHS = {"/", "/health", "/ready"}


class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)
        token = request.headers.get("X-Internal-Token", "")
        if not settings.internal_token or not hmac.compare_digest(token, settings.internal_token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
