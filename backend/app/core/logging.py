"""
프로덕션 구조화 로깅 모듈.

두 가지 출력 스트림:
1. 시스템 로그: structlog -> JSON을 stdout으로 출력 (로그 수집, 모니터링용)
2. 사용자 로그: state["logs"] 리스트 (프론트엔드 표시용)

structlog 프로세서가 contextvars에서 컨텍스트를 자동으로 주입합니다.
"""

import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import structlog

from .context import (
    get_request_id,
    get_thread_id,
    get_agent_name,
    get_node_name,
    get_step,
)


# ============================================================
# structlog 프로세서
# ============================================================

def inject_context_vars(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """모든 contextvars를 로그 이벤트에 자동으로 주입하는 프로세서."""
    ctx_fields = {
        "request_id": get_request_id(),
        "thread_id": get_thread_id(),
        "agent_name": get_agent_name(),
        "node_name": get_node_name(),
        "step": get_step(),
    }
    for key, value in ctx_fields.items():
        if value is not None and key not in event_dict:
            event_dict[key] = value
    return event_dict


# ============================================================
# 설정
# ============================================================

def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
    environment: str = "production",
) -> None:
    """
    애플리케이션 전체에 structlog를 설정합니다. 시작 시 한 번만 호출하세요.

    Args:
        log_level: 최소 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        json_output: True이면 JSON 라인 출력 (프로덕션용)
        environment: "production" 또는 "development"
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        inject_context_vars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # stdlib 로깅을 structlog를 통해 라우팅하도록 설정
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 외부 라이브러리의 불필요한 로그 레벨을 WARNING으로 제한
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "requests", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ============================================================
# 로거 팩토리
# ============================================================

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    이름이 지정된 structlog 로거를 반환합니다.

    서비스에서의 사용 예시:
        logger = get_logger("recommend_products")
        logger.info("persona_info_fetched", persona_name="Kim")

    contextvars에서 request_id, thread_id 등을 자동으로 포함합니다.
    """
    return structlog.get_logger(name)


# ============================================================
# AgentLogger -- 그래프 노드용 이중 스트림 로거
# ============================================================

class AgentLogger:
    """
    LangGraph 노드 함수용 이중 스트림 로거.

    스트림 1 (시스템): structlog JSON을 stdout으로 출력
    스트림 2 (사용자): 사람이 읽을 수 있는 문자열을 state["logs"]에 추가

    노드에서의 사용 예시:
        logger = AgentLogger(state, node_name="parse_crm_request_node")
        logger.info("Parsing started", user_message="파싱 시작")
        # ... 작업 수행 ...
        logger.info("Parsing complete", user_message="파싱 완료")
        return {
            "logs": logger.get_user_logs(),
            ...
        }
    """

    def __init__(
        self,
        state: Dict[str, Any],
        node_name: str,
        agent_name: str = "crm_agent",
    ):
        self._node_name = node_name
        self._agent_name = agent_name
        self._step = state.get("step", 0)

        # 현재 state에서 사용자 로그 초기화
        self._user_logs: List[str] = list(state.get("logs", []))

        # structlog 로거 가져오기
        self._slog = get_logger(node_name)

        # 현재 노드 스코프에 contextvars 설정
        from .context import set_node_name, set_step, set_agent_name
        set_node_name(node_name)
        set_step(self._step)
        set_agent_name(agent_name)

    def _log(
        self,
        level: str,
        message: str,
        user_message: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        내부 메서드: 두 스트림에 동시에 로그를 출력합니다.

        Args:
            level: "debug", "info", "warning", "error"
            message: 시스템 로그용 기술 메시지
            user_message: state["logs"]에 추가할 사용자용 메시지.
                          None이면 message를 그대로 사용합니다.
            **kwargs: 시스템 로그 JSON에 포함할 구조화 필드
        """
        # 스트림 1: structlog (시스템)
        log_fn = getattr(self._slog, level)
        log_fn(message, **kwargs)

        # 스트림 2: 사용자 로그 (state["logs"])
        if user_message is not None:
            self._user_logs.append(f"[Step {self._step}] {user_message}")
        else:
            self._user_logs.append(f"[Step {self._step}] {message}")

    def debug(self, message: str, user_message: Optional[str] = None, **kw: Any) -> None:
        """디버그: 시스템 로그만 기록 (user_message가 있으면 사용자 로그에도 추가)."""
        self._slog.debug(message, **kw)
        if user_message is not None:
            self._user_logs.append(f"[Step {self._step}] {user_message}")

    def info(self, message: str, user_message: Optional[str] = None, **kw: Any) -> None:
        self._log("info", message, user_message, **kw)

    def warning(self, message: str, user_message: Optional[str] = None, **kw: Any) -> None:
        self._log("warning", message, user_message, **kw)

    def error(self, message: str, user_message: Optional[str] = None, exc_info: bool = False, **kw: Any) -> None:
        if exc_info:
            kw["exc_info"] = True
        self._log("error", message, user_message, **kw)

    def get_user_logs(self) -> List[str]:
        """state['logs']에 저장할 누적된 사용자 로그를 반환합니다."""
        return self._user_logs

    @contextmanager
    def track_duration(self, operation: str, user_message: Optional[str] = None):
        """
        작업 소요 시간을 측정하고 로깅하는 컨텍스트 매니저.

        사용 예시:
            with logger.track_duration("llm_call", user_message="LLM 호출 중..."):
                result = llm.invoke(prompt)

        출력:
            시스템 로그: {"event": "llm_call_completed", "operation": "llm_call", "duration_ms": 1234.5}
            사용자 로그: "[Step 1] LLM 호출 중... 완료 (1234ms)"
        """
        start = time.perf_counter()
        if user_message:
            self._user_logs.append(f"[Step {self._step}] {user_message}")
        self._slog.info(f"{operation}_started", operation=operation)
        try:
            yield
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            self._slog.error(
                f"{operation}_failed",
                operation=operation,
                duration_ms=round(duration_ms, 1),
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            self._user_logs.append(
                f"[Step {self._step}] {operation} 실패: {str(e)}"
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            self._slog.info(
                f"{operation}_completed",
                operation=operation,
                duration_ms=round(duration_ms, 1),
            )
            self._user_logs.append(
                f"[Step {self._step}] {user_message or operation} 완료 ({int(duration_ms)}ms)"
            )
