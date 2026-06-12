-- ============================================================
-- Rate Limiter: rate_limits 테이블
-- PostgresRateLimiter (두-버킷 슬라이딩 윈도우) 전용
-- ============================================================
CREATE TABLE IF NOT EXISTS rate_limits (
    key          VARCHAR(255) PRIMARY KEY,
    count        INTEGER      NOT NULL DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    prev_count   INTEGER      NOT NULL DEFAULT 0
);
