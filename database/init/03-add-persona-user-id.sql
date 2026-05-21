-- Migration: personas 테이블에 user_id 컬럼 추가
-- 기존 DB에서 실행 필요 (Docker 재시작 시에는 01-create-tables.sql이 적용되므로 불필요)

ALTER TABLE personas ADD COLUMN IF NOT EXISTS user_id VARCHAR(100) NULL DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_personas_user_id ON personas(user_id);
