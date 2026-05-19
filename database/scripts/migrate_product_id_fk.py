"""기존 DB에 generated_messages.product_id FK 제약을 추가한다. 멱등."""
import sys
import os
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import engine

_STMTS = [
    """
    UPDATE generated_messages
    SET product_id = NULL
    WHERE product_id IS NOT NULL
      AND product_id NOT IN (SELECT product_id FROM products)
    """,
    """
    ALTER TABLE generated_messages
        ALTER COLUMN product_id DROP NOT NULL
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_generated_messages_product_id'
              AND table_name = 'generated_messages'
        ) THEN
            ALTER TABLE generated_messages
                ADD CONSTRAINT fk_generated_messages_product_id
                FOREIGN KEY (product_id)
                REFERENCES products(product_id)
                ON DELETE SET NULL;
        END IF;
    END $$
    """,
]


def apply_migration() -> None:
    with engine.connect() as conn:
        for stmt in _STMTS:
            conn.execute(text(stmt))
        conn.commit()
    print("Migration applied: generated_messages.product_id FK")


if __name__ == "__main__":
    apply_migration()
