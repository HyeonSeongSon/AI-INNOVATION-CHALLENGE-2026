-- 데이터베이스 초기화 스크립트
-- 이 파일은 컨테이너가 처음 시작될 때 자동으로 실행됩니다.

-- 예제: 테이블 생성
-- CREATE TABLE IF NOT EXISTS users (
--     id SERIAL PRIMARY KEY,
--     username VARCHAR(50) UNIQUE NOT NULL,
--     email VARCHAR(100) UNIQUE NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

-- 예제: 인덱스 생성
-- CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 예제: 초기 데이터 삽입
-- INSERT INTO users (username, email) VALUES ('admin', 'admin@example.com')
-- ON CONFLICT (username) DO NOTHING;

-- PostgreSQL 확장 설치 (필요한 경우)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";

SELECT 'Database initialized successfully!' AS status;
