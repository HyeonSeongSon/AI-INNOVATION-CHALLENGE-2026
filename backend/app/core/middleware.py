"""
요청/응답 로깅 및 상관관계 ID를 위한 FastAPI 미들웨어.

모든 수신 요청에 고유한 request_id가 부여되며,
contextvars를 통해 전체 에이전트 실행 과정에 전파됩니다.
"""

import time
import traceback
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .context import generate_request_id, set_request_id
from .logging import get_logger

logger = get_logger("http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    미들웨어 기능:
    1. 요청마다 고유한 request_id 생성
    2. contextvars에 설정 (모든 하위 로그에 자동 전파)
    3. 요청 시작 및 응답 완료를 소요 시간과 함께 로깅
    4. 응답 헤더에 X-Request-ID 추가
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 상관관계 ID 생성 및 설정
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        set_request_id(request_id)

        # 엔드포인트에서 접근할 수 있도록 request.state에 저장
        request.state.request_id = request_id

        # 요청 메타데이터 추출
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        logger.info(
            "request_started",
            method=method,
            path=path,
            client=client_host,
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 1),
            )

            # 응답에 상관관계 헤더 추가
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "request_failed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 1),
                error_type=type(e).__name__,
                error_message=str(e),
                traceback=traceback.format_exc(),
            )
            raise
