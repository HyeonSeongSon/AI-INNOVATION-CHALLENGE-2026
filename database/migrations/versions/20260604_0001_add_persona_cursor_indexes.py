"""add persona cursor indexes

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-04

커서 기반 페이지네이션을 위한 복합 인덱스 추가.
- ix_personas_cur: 어드민 전체 조회용 (persona_created_at DESC, persona_id DESC)
- ix_personas_user_cur: 일반 유저 필터 조회용 (user_id, persona_created_at DESC, persona_id DESC)
"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_personas_cur",
        "personas",
        ["persona_created_at", "persona_id"],
        postgresql_ops={
            "persona_created_at": "DESC",
            "persona_id": "DESC",
        },
    )
    op.create_index(
        "ix_personas_user_cur",
        "personas",
        ["user_id", "persona_created_at", "persona_id"],
        postgresql_ops={
            "persona_created_at": "DESC",
            "persona_id": "DESC",
        },
    )


def downgrade() -> None:
    op.drop_index("ix_personas_user_cur", table_name="personas")
    op.drop_index("ix_personas_cur", table_name="personas")
