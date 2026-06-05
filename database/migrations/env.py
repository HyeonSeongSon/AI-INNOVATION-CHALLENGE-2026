import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
MIGRATIONS_DIR = Path(__file__).resolve().parent
DATABASE_DIR = MIGRATIONS_DIR.parent
BACKEND_DIR = DATABASE_DIR.parent / "backend"

for p in (str(DATABASE_DIR), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# .env 로드 (모델 import 전에 환경변수 필요)
try:
    from dotenv import load_dotenv
    load_dotenv(DATABASE_DIR / ".env")
    load_dotenv(BACKEND_DIR / "app" / ".env")
except ImportError:
    pass

# ── Model imports ─────────────────────────────────────────────────────────────
from core.models import Base as DBBase          # database/core/models.py

try:
    from app.core.models import Base as BackendBase  # backend/app/core/models.py
    target_metadata = [DBBase.metadata, BackendBase.metadata]
except Exception:
    target_metadata = DBBase.metadata

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "ai_innovation_db")
    user = os.getenv("POSTGRES_USER", "postgres")
    pw   = os.getenv("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
