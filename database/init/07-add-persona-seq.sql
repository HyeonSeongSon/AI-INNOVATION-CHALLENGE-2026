-- ============================================================
-- persona_seq 시퀀스 생성
-- Persona 모델 server_default: 'PERSONA_' || LPAD(nextval('persona_seq')::text, 5, '0')
-- 예: PERSONA_00001, PERSONA_00002, ...
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS persona_seq;

-- personas 테이블 persona_id 컬럼에 시퀀스 기반 DEFAULT 추가
ALTER TABLE personas
    ALTER COLUMN persona_id SET DEFAULT 'PERSONA_' || LPAD(nextval('persona_seq')::text, 5, '0');
