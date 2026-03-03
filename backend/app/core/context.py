"""
contextvars 기반 요청 컨텍스트 전파 모듈.

전파 흐름:
  FastAPI 미들웨어(request_id 생성) → agent.run() → 노드 함수 → 서비스 메서드

workflow.invoke()가 동일 스레드에서 동기 실행되므로 contextvars가 자동으로 전파됩니다.
"""

import uuid
from contextvars import ContextVar
from typing import Optional


# 핵심 컨텍스트 변수
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_thread_id_var: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)
_agent_name_var: ContextVar[Optional[str]] = ContextVar("agent_name", default=None)
_node_name_var: ContextVar[Optional[str]] = ContextVar("node_name", default=None)
_step_var: ContextVar[Optional[int]] = ContextVar("step", default=None)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_thread_id() -> Optional[str]:
    return _thread_id_var.get()


def set_thread_id(thread_id: str) -> None:
    _thread_id_var.set(thread_id)


def get_agent_name() -> Optional[str]:
    return _agent_name_var.get()


def set_agent_name(name: str) -> None:
    _agent_name_var.set(name)


def get_node_name() -> Optional[str]:
    return _node_name_var.get()


def set_node_name(name: str) -> None:
    _node_name_var.set(name)


def get_step() -> Optional[int]:
    return _step_var.get()


def set_step(step: int) -> None:
    _step_var.set(step)


def generate_request_id() -> str:
    """짧은 URL-safe 요청 ID를 생성합니다."""
    return uuid.uuid4().hex[:12]


class request_context:
    """여러 컨텍스트 변수를 한꺼번에 설정하고, 스코프 종료 시 자동으로 복원하는 컨텍스트 매니저.

    사용 예시:
        with request_context(request_id="abc", thread_id="t1", agent_name="crm"):
            # 이 스코프 안에서 모든 로거에 위 필드가 자동으로 포함됩니다.
            ...
    """

    def __init__(self, **kwargs):
        self._tokens = {}
        self._setters = {
            "request_id": _request_id_var,
            "thread_id": _thread_id_var,
            "agent_name": _agent_name_var,
            "node_name": _node_name_var,
            "step": _step_var,
        }
        self._values = kwargs

    def __enter__(self):
        for key, value in self._values.items():
            if key in self._setters and value is not None:
                self._tokens[key] = self._setters[key].set(value)
        return self

    def __exit__(self, *args):
        for key, token in self._tokens.items():
            self._setters[key].reset(token)
