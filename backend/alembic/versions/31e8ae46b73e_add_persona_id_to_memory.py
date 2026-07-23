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


def downgrade() -> None:
    op.drop_index("ix_memory_user_persona", table_name="memory")
    op.drop_constraint("memory_persona_id_fkey", "memory", type_="foreignkey")
    op.drop_column("memory", "persona_id")
