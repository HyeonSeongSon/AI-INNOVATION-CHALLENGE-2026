import os
from pathlib import Path
from dotenv import load_dotenv

# .env를 한 번만 로드
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


class Settings:
    # API Keys
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")

    # Model
    chatgpt_model_name: str = os.getenv("CHATGPT_MODEL_NAME", "gpt-5-mini")
    parser_model_name: str = os.getenv("PARSER_MODEL_NAME", "gpt-5-nano")

    # External APIs
    opensearch_api_url: str = os.getenv("OPENSEARCH_API_URL", "http://localhost:8010")
    database_api_url: str = os.getenv("DATABASE_API_URL", "http://localhost:8020")

    # PostgreSQL (direct)
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "ai_innovation_db")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    # PostgreSQL (LangGraph checkpointer)
    postgres_url: str = os.getenv("POSTGRES_URL", "")

    # LangSmith
    langchain_tracing_v2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    langchain_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    langchain_project: str = os.getenv("LANGCHAIN_PROJECT", "default")
    langchain_endpoint: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "production")

    # App
    app_root: str = os.getenv("APP_ROOT", "")

    # Product recommendation tuning
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    min_rrf_score_threshold: float = float(os.getenv("MIN_RRF_SCORE_THRESHOLD", "0.01"))
    min_filtered_products: int = int(os.getenv("MIN_FILTERED_PRODUCTS", "3"))


settings = Settings()
