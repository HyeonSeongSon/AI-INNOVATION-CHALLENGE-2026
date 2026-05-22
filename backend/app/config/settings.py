from typing import Literal
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_MODEL_PREFIXES: tuple[str, ...] = ("gpt-", "o1", "o3", "o4", "claude-", "gemini-")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Model
    chatgpt_model_name: str = "gpt-5-mini"
    parser_model_name: str = "gpt-5-nano"
    chatgpt_model_temperature: float = 0.7
    parser_model_temperature: float = 0.0

    # External APIs
    opensearch_api_url: str = "http://fastapi-search:8010"
    database_api_url: str = "http://ai-innovation-db-api:8020"

    # PostgreSQL (direct)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_innovation_db"
    postgres_user: str = "postgres"
    postgres_password: str = ""

    # PostgreSQL (LangGraph checkpointer, mandatory)
    postgres_url: str = ""

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "default"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Logging
    log_level: str = "INFO"
    environment: str = "production"

    # App
    app_root: str = ""

    # Internal service-to-service token
    internal_token: str = ""

    # Auth
    auth_mode: Literal["api_key", "jwt"] = "jwt"
    service_api_key: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Rate limiting — auth endpoints
    rate_limit_login_max_requests: int = 10
    rate_limit_login_window_seconds: int = 60
    rate_limit_register_max_requests: int = 5
    rate_limit_register_window_seconds: int = 60
    trusted_proxy_ips: set[str] = set()
    trusted_proxy_count: int = 1  # 앞단 신뢰 프록시 수 (CDN+Nginx 체인이면 2)

    # Account lockout (per IP-email 쌍 기준 — 전역 계정 잠금 대신 사용)
    account_lockout_max_attempts: int = 10    # 하위 호환용 — 실제 잠금 로직은 lockout_per_ip_* 사용
    account_lockout_duration_seconds: int = 900
    lockout_per_ip_max_attempts: int = 10     # 동일 IP-이메일 쌍에서 최대 실패 횟수
    lockout_per_ip_window_seconds: int = 900  # 잠금 지속 시간 (기본 15분)

    # A2A URLs
    recommend_agent_url: str = "http://localhost:8001"
    generate_message_agent_url: str = "http://localhost:8002"
    data_registration_agent_url: str = "http://localhost:8003"
    a2a_timeout: float = 120.0
    a2a_max_retries: int = 3

    # CORS — 환경변수에서 콤마 구분 문자열로 받아 list[str]로 파싱
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8005

    # HTTP client timeouts (seconds)
    http_timeout_short: float = 10.0
    http_timeout_default: float = 15.0
    http_timeout_long: float = 30.0
    http_timeout_upload: float = 60.0

    # LLM call timeouts (seconds)
    llm_timeout: float = 60.0
    llm_call_timeout: float = 70.0
    llm_document_timeout: float = 150.0

    # LangGraph
    langgraph_recursion_limit: int = 100

    # Product recommendation tuning
    rrf_k: int = 60
    min_rrf_score_threshold: float = 0.01
    min_filtered_products: int = 3

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def parse_trusted_proxy_ips(cls, v: object) -> object:
        if isinstance(v, str):
            return {ip.strip() for ip in v.split(",") if ip.strip()}
        return v

    @field_validator("chatgpt_model_name", "parser_model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        if not any(v.startswith(p) for p in ALLOWED_MODEL_PREFIXES):
            raise ValueError(
                f"지원하지 않는 모델명: {v}. 지원 접두사: {', '.join(ALLOWED_MODEL_PREFIXES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "Settings":
        if not self.postgres_url:
            raise ValueError("POSTGRES_URL 환경변수가 설정되지 않았습니다.")
        if not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD 환경변수가 설정되지 않았습니다.")
        if not self.internal_token:
            raise ValueError("INTERNAL_TOKEN 환경변수가 설정되지 않았습니다.")
        if self.auth_mode == "api_key" and not self.service_api_key:
            raise ValueError("AUTH_MODE=api_key일 때 SERVICE_API_KEY가 필요합니다.")
        if self.auth_mode == "jwt":
            if not self.jwt_secret:
                raise ValueError("AUTH_MODE=jwt일 때 JWT_SECRET이 필요합니다.")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET은 최소 32자 이상이어야 합니다.")

        # 설정된 모델에 필요한 API 키 검증 — 서버 시작 시점에 fail-fast
        active_models = [self.chatgpt_model_name, self.parser_model_name]
        openai_prefixes = ("gpt-", "o1", "o3", "o4")
        if any(m.startswith(openai_prefixes) for m in active_models) and not self.openai_api_key:
            raise ValueError(
                "OpenAI 모델이 설정되어 있지만 OPENAI_API_KEY가 비어 있습니다."
            )
        if any(m.startswith("claude-") for m in active_models) and not self.anthropic_api_key:
            raise ValueError(
                "Anthropic 모델이 설정되어 있지만 ANTHROPIC_API_KEY가 비어 있습니다."
            )
        if any(m.startswith("gemini-") for m in active_models) and not self.google_api_key:
            raise ValueError(
                "Google 모델이 설정되어 있지만 GOOGLE_API_KEY가 비어 있습니다."
            )

        # LangSmith 트레이싱 활성화 시 API 키 필요
        if self.langchain_tracing_v2 and not self.langchain_api_key:
            raise ValueError(
                "LANGCHAIN_TRACING_V2=true일 때 LANGCHAIN_API_KEY가 필요합니다."
            )

        return self


settings = Settings()
