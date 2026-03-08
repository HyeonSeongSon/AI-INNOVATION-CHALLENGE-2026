"""
Database Connection and Session Management
PostgreSQL 데이터베이스 연결 관리
"""

import os
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from core.models import Base

# .env 파일 로드
load_dotenv()


class DatabaseConfig:
    """데이터베이스 설정"""

    def __init__(self):
        self.host = os.getenv('POSTGRES_HOST', 'localhost')
        self.port = int(os.getenv('POSTGRES_PORT', 5432))
        self.database = os.getenv('POSTGRES_DB', 'ai_innovation_db')
        self.user = os.getenv('POSTGRES_USER', 'postgres')
        self.password = os.getenv('POSTGRES_PASSWORD', '')

    @property
    def database_url(self) -> str:
        """PostgreSQL 연결 URL 생성"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


# 데이터베이스 설정 인스턴스
db_config = DatabaseConfig()

# SQLAlchemy 엔진 생성
engine = create_engine(
    db_config.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 세션 팩토리 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database initialized: {db_config.database}")


def drop_all_tables():
    Base.metadata.drop_all(bind=engine)
    print(f"⚠️  All tables dropped from: {db_config.database}")


def check_connection() -> bool:
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Database connection successful: {db_config.host}:{db_config.port}/{db_config.database}")
        return True
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return False
