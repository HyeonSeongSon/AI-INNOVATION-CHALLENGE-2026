from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseAgent(ABC):
    """
    모든 Agent의 공통 베이스 클래스

    역할:
    - workflow(graph) 생성
    - 실행 인터페이스 제공
    - state 초기화
    - 공통 실행 로직 관리
    """

    def __init__(
        self,
        llm: Any,
        config: Optional[Dict] = None,
    ):
        self.llm = llm
        self.config = config or {}

        # 그래프는 하위 클래스에서 구현
        self.graph = self._build_workflow()

# -------------------------------------------------
# 필수 구현 영역
# -------------------------------------------------

    @abstractmethod
    def _build_workflow(self):
        """
        LangGraph workflow 생성
        반드시 하위 Agent에서 구현해야 함
        """
        pass

    @abstractmethod
    def _create_initial_state(self, **kwargs):
        """
        초기 State 생성
        """
        pass

  # -------------------------------------------------
  # 공통 실행 메서드
  # -------------------------------------------------

    def run(self, **kwargs):
        """
        동기 실행
        """

        state = self._create_initial_state(**kwargs)

        result = self.graph.invoke(state)

        return result

    async def arun(self, **kwargs):
        """
        비동기 실행
        """

        state = self._create_initial_state(**kwargs)

        result = await self.graph.ainvoke(state)

        return result

    def stream(self, **kwargs):
        """
        Streaming 실행 (LangGraph stream 대응)
        """

        state = self._create_initial_state(**kwargs)

        for event in self.graph.stream(state):
            yield event

    async def astream(self, **kwargs):
        """
        Async Streaming
        """

        state = self._create_initial_state(**kwargs)

        async for event in self.graph.astream(state):
            yield event

# -------------------------------------------------
# interrupt / resume 지원
# -------------------------------------------------

    def resume(self, state):
        """
        interrupt 이후 resume
        """

        return self.graph.invoke(state)

    async def aresume(self, state):
        return await self.graph.ainvoke(state)