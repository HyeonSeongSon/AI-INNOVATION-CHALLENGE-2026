import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional, Generator

# 환경 변수 로드 (.env 파일 경로 지정)
current_dir = Path(__file__).resolve().parent
env_path = current_dir.parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 환경 변수 키 매핑
ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY"
}

class LLMService:
    """
    OpenAI, Claude, Gemini를 지원하는 멀티 모델 LLM 서비스
    """

    def __init__(
        self,
        model_type: str,
        model_name: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """
        지정된 모델로 LLM 서비스 초기화

        Args:
            model_type: "openai", "claude", "gemini" 중 선택
            model_name: 사용할 모델명 
                예: "gpt-4", "claude-3-opus-20240229", "gemini-1.5-flash"
            temperature: 모델 온도 
            max_tokens: 최대 토큰 수
        """
        self.model_type = model_type.lower()

        if self.model_type not in ENV_KEYS:
            raise ValueError(
                f"지원하지 않는 모델 타입: {self.model_type}. "
                f"사용 가능한 모델: {', '.join(ENV_KEYS.keys())}"
            )

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = self._initialize_model()

    def _initialize_model(self):
        """model_type에 따라 적절한 모델 초기화"""

        # .env에서 API 키 가져오기
        env_key = ENV_KEYS[self.model_type]
        api_key = os.getenv(env_key)

        if not api_key:
            raise ValueError(
                f"환경 변수에서 {env_key}를 찾을 수 없습니다. "
                f".env 파일에 {env_key}를 설정해주세요."
            )

        if self.model_type == "openai":
            return ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=api_key
            )

        elif self.model_type == "claude":
            return ChatAnthropic(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=api_key
            )

        elif self.model_type == "gemini":
            return ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                google_api_key=api_key
            )

    def invoke(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        모델에 메시지를 전송하고 응답을 받음

        Args:
            message: 사용자 메시지
            system_prompt: 선택적 시스템 프롬프트

        Returns:
            모델 응답 문자열
        """
        messages = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=message))

        response = self.model.invoke(messages)
        return response.content

    async def ainvoke(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        invoke의 비동기 버전

        Args:
            message: 사용자 메시지
            system_prompt: 선택적 시스템 프롬프트

        Returns:
            모델 응답 문자열
        """
        messages = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=message))

        response = await self.model.ainvoke(messages)
        return response.content

    def stream(
        self,
        message: str,
        system_prompt: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        모델로부터 스트리밍 응답 받기

        Args:
            message: 사용자 메시지
            system_prompt: 선택적 시스템 프롬프트

        Yields:
            모델 응답의 청크들
        """
        messages = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=message))

        for chunk in self.model.stream(messages):
            yield chunk.content

    def get_model_info(self) -> dict:
        """현재 모델 정보 가져오기"""
        return {
            "model_type": self.model_type,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }