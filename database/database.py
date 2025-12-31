from sqlmodel import SQLModel, create_engine, Session
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경변수에서 DB 정보 가져오기 (기본값 설정)
POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ai_innovation_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres-db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# PostgreSQL 연결 URL
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# 엔진 생성
engine = create_engine(DATABASE_URL, echo=True)

def init_db():
    """
    서버 시작 시 호출되어 테이블을 생성합니다.
    SQLModel을 상속받은 모든 클래스(models.py)를 찾아 테이블로 만듭니다.
    """
    SQLModel.metadata.create_all(engine)

def get_db():
    """API 요청 시마다 DB 세션을 열고 닫습니다."""
    with Session(engine) as session:
        yield session