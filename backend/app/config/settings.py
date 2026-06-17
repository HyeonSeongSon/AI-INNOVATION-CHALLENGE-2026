from typing import Literal
from pathlib import Path
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_MODEL_PREFIXES: tuple[str, ...] = ("gpt-", "o1", "o3", "o4", "claude-", "gemini-")

_WEAK_SECRET_FRAGMENTS: frozenset[str] = frozenset({
    "secret", "changeme", "password", "example", "test",
    "jwt", "token", "internal", "your-secret", "replace",
    "abcdef", "123456",
})


def _is_weak_secret(value: str) -> bool:
    lower = value.lower()
    if any(frag in lower for frag in _WEAK_SECRET_FRAGMENTS):
        return True
    if len(set(value)) < 6:
        return True
    return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).parent.parent / ".env",
            Path(__file__).parent.parent / ".env.local",  # 로컬 오버라이드 (없으면 무시)
        ],
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
    service_api_key_user_id: str = ""  # AUTH_MODE=api_key 시 API Key에 매핑할 서버 측 고정 user_id
    jwt_secret: str = ""
    jwt_algorithm: Literal["HS256", "HS384", "HS512", "RS256"] = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    user_assertion_expire_seconds: int = 30

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

    # Rate limiting — LLM chat endpoints (per-user)
    rate_limit_chat_max_requests: int = 100
    rate_limit_chat_window_seconds: int = 3600  # 1시간당 100회

    # Rate limiting — auth token endpoints (per-IP)
    rate_limit_refresh_max_requests: int = 30
    rate_limit_refresh_window_seconds: int = 600   # 10분당 30회
    rate_limit_logout_max_requests: int = 20
    rate_limit_logout_window_seconds: int = 60     # 1분당 20회

    # Rate limiting — persona pipeline endpoints (per-user)
    rate_limit_persona_text_max_requests: int = 20
    rate_limit_persona_text_window_seconds: int = 3600   # 1시간당 20회
    rate_limit_persona_upload_max_requests: int = 20
    rate_limit_persona_upload_window_seconds: int = 3600  # 1시간당 20회

    # Rate limiting — DB write endpoints (per-user)
    rate_limit_conversation_write_max_requests: int = 100
    rate_limit_conversation_write_window_seconds: int = 3600  # 1시간당 100회
    rate_limit_persona_delete_max_requests: int = 30
    rate_limit_persona_delete_window_seconds: int = 3600      # 1시간당 30회

    # Rate limiting — admin product upload (per-user)
    rate_limit_product_upload_max_requests: int = 10
    rate_limit_product_upload_window_seconds: int = 86400  # 1일당 10회

    # DB cleanup background worker
    cleanup_interval_seconds: int = 3600
    cleanup_token_grace_days: int = 1
    max_refresh_tokens_per_user: int = 10  # 1명당 동시 활성 토큰 상한

    # LangGraph checkpoint retention
    checkpoint_retention_days: int = 30       # 마지막 체크포인트 기준 보존 기간 (일)
    checkpoint_cleanup_batch_size: int = 500  # 1회 삭제 최대 thread 수 (락 경합 방지)

    # A2A URLs
    recommend_agent_url: str = "http://localhost:8001"
    generate_message_agent_url: str = "http://localhost:8002"
    data_registration_agent_url: str = "http://localhost:8003"
    a2a_timeout: float = 280.0
    a2a_max_retries: int = Field(default=3, ge=1)

    # CRM Service (내부 전용)
    crm_service_url: str = "http://localhost:8006"

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

    # File upload background job
    upload_job_ttl_seconds: int = 3600
    upload_job_done_ttl_seconds: int = 300      # 완료/에러 job 5분 후 제거
    max_active_jobs_per_user: int = 5           # 사용자당 동시 활성 job 상한
    upload_file_read_timeout: float = 30.0
    upload_file_parse_timeout: float = 15.0
    upload_job_max_seconds: int = 7200           # 배치 잡 전체 최대 실행 시간 (기본 2시간)

    # LLM call timeouts (seconds)
    llm_timeout: float = 60.0
    llm_call_timeout: float = 70.0
    llm_document_timeout: float = 300.0
    llm_registration_sdk_timeout: float = 330.0  # 상품 등록 LLM SDK 타임아웃 (llm_document_timeout보다 여유있게)

    # LangGraph
    langgraph_recursion_limit: int = 100
    graph_execution_timeout: float = 600.0

    # Product recommendation tuning
    rrf_k: int = 60
    min_rrf_score_threshold: float = 0.01
    min_filtered_products: int = 3

    # OpenSearch index names
    opensearch_product_index: str = "product_index_v3"
    opensearch_hybrid_pipeline: str = "hybrid-minmax-pipeline"
    opensearch_v4_combined_index: str = "product_v4_combined"
    opensearch_v4_function_desc_index: str = "product_v4_function_desc"
    opensearch_v4_attribute_desc_index: str = "product_v4_attribute_desc"
    opensearch_v4_target_user_index: str = "product_v4_target_user"
    opensearch_v4_spec_feature_index: str = "product_v4_spec_feature"
    opensearch_forbidden_sentences_index: str = "forbidden_sentences"

    # Quality check — rule-based message length
    message_title_max_length: int = 40
    message_body_min_length: int = 20
    message_body_max_length: int = 350

    # Quality check — semantic similarity
    quality_check_semantic_threshold: float = 0.85
    quality_check_semantic_top_k: int = 3
    quality_check_semantic_max_retries: int = 2
    quality_check_retry_backoff_base: float = 0.5

    # Quality check — LLM judge scoring
    quality_check_llm_min_score: int = 3
    quality_check_llm_min_overall_score: int = 4

    # HTTP streaming timeouts (SSE proxy)
    http_timeout_stream_connect: float = 10.0
    http_timeout_stream_pool: float = 5.0

    # SSE keepalive & file upload
    sse_keepalive_timeout: float = 25.0
    sse_stream_max_seconds: int = 7320  # upload_job_max_seconds(7200) + 120s 버퍼
    max_upload_bytes: int = 52428800  # 50 * 1024 * 1024

    # Chat request body size limit (미들웨어에서 강제 적용)
    max_chat_body_bytes: int = 10 * 1024 * 1024  # 10MB

    # Upload concurrency
    upload_persona_concurrency: int = 5
    upload_product_concurrency: int = 3
    max_records_per_upload: int = 10000

    # Conversation management
    conversation_summarize_threshold: int = 30
    conversation_keep_messages: int = 10

    # Database pool (SQLAlchemy sync)
    db_pool_size: int = 10
    db_pool_max_overflow: int = 20
    db_pool_recycle_seconds: int = 3600

    # Database pool (psycopg async — LangGraph checkpointer)
    postgres_async_pool_min_size: int = 1
    postgres_async_pool_max_size: int = 30

    # OpenSearch 동시 검색 요청 상한 (세마포어)
    opensearch_max_concurrent_searches: int = 20

    # Health check
    health_check_db_timeout: float = 2.0

    # Product retrieval
    product_retrieval_top_k: int = 100
    product_recommendation_top_n: int = 3

    # Image chunk processing
    image_chunk_height_max: int = 4000
    image_chunk_overlap: int = 100
    image_max_chunks: int = 10

    # A2A retry backoff
    a2a_retry_backoff_base: float = 2.0
    a2a_retry_backoff_max: float = 30.0

    # OpenSearch 색인 재시도 (backoff은 a2a_retry_backoff_base/max 재사용)
    opensearch_index_max_retries: int = Field(default=3, ge=1)

    # LLM temperatures (역할별)
    llm_temperature_classifier: float = 0.0
    llm_temperature_generator: float = 0.7
    llm_temperature_creative: float = 0.5
    llm_temperature_persona: float = 0.3
    llm_temperature_vision: float = 0.0
    llm_temperature_document: float = 0.7

    # Admin seed — 최초 배포 시 admin 계정 자동 생성, 이후 Secrets Manager 삭제로 비활성화
    admin_seed_email: str = ""
    admin_seed_password: str = ""

    # AWS — self-cleaning seed secrets용 (Terraform var.project_name, var.aws_region과 일치)
    aws_region: str = "ap-northeast-2"
    project_name: str = "ai-innovation"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        if isinstance(v, list):
            return [o for o in v if isinstance(o, str) and o.strip()]
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
        if len(self.internal_token) < 32:
            raise ValueError(
                "INTERNAL_TOKEN은 최소 32자 이상이어야 합니다. "
                "'openssl rand -hex 32'로 생성하세요."
            )
        if _is_weak_secret(self.internal_token):
            raise ValueError(
                "INTERNAL_TOKEN에 예측 가능한 패턴이 포함되어 있습니다. "
                "'openssl rand -hex 32'로 재생성하세요."
            )
        if self.auth_mode == "api_key" and not self.service_api_key:
            raise ValueError("AUTH_MODE=api_key일 때 SERVICE_API_KEY가 필요합니다.")
        if self.auth_mode == "api_key" and not self.service_api_key_user_id:
            raise ValueError(
                "AUTH_MODE=api_key일 때 SERVICE_API_KEY_USER_ID가 필요합니다. "
                "API Key에 매핑할 서비스 계정 ID를 설정하세요."
            )
        if self.auth_mode == "jwt":
            if not self.jwt_secret:
                raise ValueError("AUTH_MODE=jwt일 때 JWT_SECRET이 필요합니다.")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET은 최소 32자 이상이어야 합니다.")
            if _is_weak_secret(self.jwt_secret):
                raise ValueError(
                    "JWT_SECRET에 예측 가능한 패턴이 포함되어 있습니다. "
                    "'openssl rand -hex 32'로 재생성하세요."
                )
            if self.jwt_secret == self.internal_token:
                raise ValueError(
                    "JWT_SECRET과 INTERNAL_TOKEN은 반드시 다른 값이어야 합니다. "
                    "각각 'openssl rand -hex 32'로 별도 생성하세요."
                )

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

        if self.environment == "production" and not self.trusted_proxy_ips:
            raise ValueError(
                "프로덕션 환경에서 TRUSTED_PROXY_IPS가 비어 있으면 IP 기반 Rate Limit이 "
                "무효화됩니다. Nginx IP를 TRUSTED_PROXY_IPS 환경변수에 추가하세요. "
                "예: TRUSTED_PROXY_IPS=10.0.0.1"
            )

        if self.environment == "production":
            localhost_origins = [
                o for o in self.allowed_origins
                if "localhost" in o or "127.0.0.1" in o
            ]
            if localhost_origins:
                raise ValueError(
                    f"프로덕션 환경에서 localhost CORS 오리진이 설정되어 있습니다: {localhost_origins}. "
                    "실제 프론트엔드 도메인으로 교체하세요. "
                    "예: ALLOWED_ORIGINS=https://your-domain.com"
                )
            if not self.allowed_origins:
                raise ValueError(
                    "프로덕션 환경에서 ALLOWED_ORIGINS가 비어 있습니다. "
                    "GitHub Secret에 프론트엔드 도메인을 설정하세요. "
                    "예: ALLOWED_ORIGINS=https://your-domain.com"
                )

        # LangSmith 트레이싱 활성화 시 API 키 필요
        if self.langchain_tracing_v2 and not self.langchain_api_key:
            raise ValueError(
                "LANGCHAIN_TRACING_V2=true일 때 LANGCHAIN_API_KEY가 필요합니다."
            )

        return self


settings = Settings()
