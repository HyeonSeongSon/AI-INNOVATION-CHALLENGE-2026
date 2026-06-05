"""
ASGI 미들웨어: HTTP 요청 바디 크기 제한

두 단계로 차단:
1. Content-Length 헤더 확인 → early rejection (413)
2. receive() 래핑 → chunked transfer encoding도 실제 바이트 누적으로 차단
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class PayloadTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except ValueError:
                content_length = 0
            if content_length > self.max_body_bytes:
                await self._send_413(send)
                return

        total_bytes = 0

        async def limited_receive() -> dict:
            nonlocal total_bytes
            message = await receive()
            if message.get("type") == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_body_bytes:
                    raise PayloadTooLargeError(
                        f"요청 바디가 최대 허용 크기({self.max_body_bytes} bytes)를 초과했습니다."
                    )
            return message

        try:
            await self.app(scope, limited_receive, send)
        except PayloadTooLargeError:
            await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        import json
        body = json.dumps({"detail": "요청 바디가 너무 큽니다."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
