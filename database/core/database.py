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
        password = os.getenv('POSTGRES_PASSWORD')
        if password is None:
            raise ValueError("POSTGRES_PASSWORD 환경변수가 설정되지 않았습니다.")
        self.password = password
        # Postgres max_connections(기본 100) 중 관리자/마이그레이션용으로 일부를 남기고
        # 앱이 쓸 수 있는 실질 한도를 pool_size+max_overflow로 설정한다.
        self.pool_size = int(os.getenv('DB_POOL_SIZE', 20))
        self.max_overflow = int(os.getenv('DB_MAX_OVERFLOW', 60))
        # 동기 DB 세션 의존성(get_db)이 실행되는 anyio 스레드풀 capacity.
        # pool_size+max_overflow보다 작으면 풀 증설 효과가 무력화되므로 그 이상으로 맞춘다.
        self.db_threadpool_capacity = int(os.getenv('DB_THREADPOOL_CAPACITY', 100))

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
    pool_size=db_config.pool_size,
    max_overflow=db_config.max_overflow,
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
