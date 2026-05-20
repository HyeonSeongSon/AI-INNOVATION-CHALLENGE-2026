from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    opensearch_api_url: str = "http://localhost:8010"
    database_api_url: str = "http://localhost:8020"

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

    # Auth
    auth_mode: str = "api_key"
    service_api_key: str = ""
    jwt_secret: str = ""

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

    @field_validator("chatgpt_model_name", "parser_model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        valid_prefixes = ("gpt-", "o1", "o3", "o4", "claude-", "gemini-")
        if not any(v.startswith(p) for p in valid_prefixes):
            raise ValueError(
                f"지원하지 않는 모델명: {v}. 지원 접두사: {', '.join(valid_prefixes)}"
            )
        return v

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "Settings":
        if not self.postgres_url:
            raise ValueError("POSTGRES_URL 환경변수가 설정되지 않았습니다.")
        if self.auth_mode == "api_key" and not self.service_api_key:
            raise ValueError("AUTH_MODE=api_key일 때 SERVICE_API_KEY가 필요합니다.")
        if self.auth_mode == "jwt":
            raise NotImplementedError(
                "AUTH_MODE=jwt는 아직 구현되지 않았습니다. 현재는 AUTH_MODE=api_key만 지원합니다."
            )
        return self


settings = Settings()
