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

from app.core.models import Base

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
    echo=False,  # SQL 쿼리 로깅 (개발 시 True로 변경)
    pool_size=10,  # 커넥션 풀 크기
    max_overflow=20,  # 최대 오버플로우
    pool_pre_ping=True,  # 연결 유효성 검사
    pool_recycle=3600,  # 1시간마다 연결 재사용
)

# 세션 팩토리 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# SQLite 호환성을 위한 이벤트 리스너 (PostgreSQL에서는 필요 없지만 호환성 유지)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """SQLite PRAGMA 설정 (PostgreSQL에서는 무시됨)"""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    데이터베이스 세션 제너레이터

    Usage:
        with get_db() as db:
            # 데이터베이스 작업 수행
            db.query(Model).all()

    또는 FastAPI Dependency Injection:
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
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
    """
    데이터베이스 초기화
    모든 테이블 생성
    """
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database initialized: {db_config.database}")


def drop_all_tables():
    """
    모든 테이블 삭제 (주의: 개발 환경에서만 사용)
    """
    Base.metadata.drop_all(bind=engine)
    print(f"⚠️  All tables dropped from: {db_config.database}")


def check_connection() -> bool:
    """
    데이터베이스 연결 확인

    Returns:
        bool: 연결 성공 여부
    """
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Database connection successful: {db_config.host}:{db_config.port}/{db_config.database}")
        return True
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return False


if __name__ == "__main__":
    """
    직접 실행 시 데이터베이스 연결 테스트

    Usage:
        python database.py
    """
    print("=" * 60)
    print("Database Connection Test")
    print("=" * 60)
    print(f"Host: {db_config.host}")
    print(f"Port: {db_config.port}")
    print(f"Database: {db_config.database}")
    print(f"User: {db_config.user}")
    print("=" * 60)

    if check_connection():
        print("\n🎉 Database is ready!")
    else:
        print("\n💥 Database connection failed. Please check your configuration.")
