-- ============================================================
-- Account lockout: users 테이블에 실패 카운터 + 잠금 만료 컬럼 추가
-- ============================================================
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;
