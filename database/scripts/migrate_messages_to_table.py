"""
conversations.messages JSON 배열 → conversation_messages 테이블 마이그레이션.
멱등성 보장: 이미 마이그레이션된 conversation은 건너뜀.

실행:
    cd database
    python scripts/migrate_messages_to_table.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from core.database import engine


def apply() -> None:
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                conversation_id VARCHAR(36) NOT NULL
                                    REFERENCES conversations(id) ON DELETE CASCADE,
                message_data    JSONB NOT NULL,
                created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_conv_messages_conv_id
                ON conversation_messages(conversation_id, id)
        """))
        conn.commit()
        print("테이블 준비 완료")

        rows = conn.execute(text("""
            SELECT id, messages FROM conversations
            WHERE messages IS NOT NULL
              AND json_array_length(messages) > 0
              AND id NOT IN (SELECT DISTINCT conversation_id FROM conversation_messages)
        """)).fetchall()

        print(f"마이그레이션 대상: {len(rows)}개 대화")
        total = 0

        for conv_id, messages in rows:
            msgs = json.loads(messages) if isinstance(messages, str) else messages
            for msg in msgs:
                conn.execute(
                    text(
                        "INSERT INTO conversation_messages (conversation_id, message_data)"
                        " VALUES (:cid, CAST(:data AS jsonb))"
                    ),
                    {"cid": conv_id, "data": json.dumps(msg, ensure_ascii=False)},
                )
                total += 1
            conn.commit()  # 대화 단위 커밋 — 중단 후 재실행 가능

        print(f"완료: {total}개 메시지 마이그레이션")


if __name__ == "__main__":
    apply()
