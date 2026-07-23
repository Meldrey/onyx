"""add persona_id to memory

Revision ID: 31e8ae46b73e
Revises: 503883791c39
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "31e8ae46b73e"
down_revision = "503883791c39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory",
        sa.Column("persona_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "memory_persona_id_fkey",
        "memory",
        "persona",
        ["persona_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_memory_user_persona",
        "memory",
        ["user_id", "persona_id"],
    )

    # --- Data migration: backfill persona_id from conversation history ---
    # Join memory → chat_session via conversation_id to resolve which persona
    # each memory belongs to. Memories without a resolvable persona are deleted.
    conn = op.get_bind()

    # Backfill persona_id where conversation_id maps to a chat_session
    conn.execute(
        sa.text("""
            UPDATE memory
            SET persona_id = cs.persona_id
            FROM chat_session cs
            WHERE memory.conversation_id = cs.id
              AND cs.persona_id IS NOT NULL
              AND memory.persona_id IS NULL
        """)
    )

    # Delete orphaned memories that couldn't be assigned to a persona:
    # - no conversation_id (manually created with no provenance)
    # - conversation_id doesn't match any chat_session
    # - chat_session has no persona_id
    conn.execute(
        sa.text("""
            DELETE FROM memory
            WHERE persona_id IS NULL
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_memory_user_persona", table_name="memory")
    op.drop_constraint("memory_persona_id_fkey", "memory", type_="foreignkey")
    op.drop_column("memory", "persona_id")
