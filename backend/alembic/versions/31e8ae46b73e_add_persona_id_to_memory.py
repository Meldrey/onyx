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

    # --- Data migration: assign existing memories to personas ---
    conn = op.get_bind()

    # Step 1: Backfill from conversation_id where possible
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

    # Step 2: Manual assignments for memories without conversation_id
    # Brick (persona_id=2): themusetechmusic brand, Nviroclean YouTube
    conn.execute(sa.text(
        "UPDATE memory SET persona_id = 2 WHERE id IN (11, 12) AND persona_id IS NULL"
    ))

    # Haugen (persona_id=5): MOOD:ME website work
    conn.execute(sa.text(
        "UPDATE memory SET persona_id = 5 WHERE id IN (13, 14, 15, 16, 17) AND persona_id IS NULL"
    ))

    # Step 3: Duplicate shared memories to all 3 agents
    # Memory 18 (accessibility) and 19 (Nviroclean spelling) → Brick, Haugen, Saltman
    for mem_id in (18, 19):
        row = conn.execute(
            sa.text("SELECT user_id, memory_text FROM memory WHERE id = :id"),
            {"id": mem_id},
        ).fetchone()
        if row:
            user_id, text = row[0], row[1]
            # Assign original to Brick
            conn.execute(sa.text(
                "UPDATE memory SET persona_id = 2 WHERE id = :id"
            ), {"id": mem_id})
            # Create copies for Haugen and Saltman
            for pid in (5, 6):
                conn.execute(
                    sa.text(
                        "INSERT INTO memory (user_id, persona_id, memory_text) "
                        "VALUES (:uid, :pid, :txt)"
                    ),
                    {"uid": str(user_id), "pid": pid, "txt": text},
                )

    # Memory 20 (weekly summaries) → duplicate to Brick and Haugen
    row = conn.execute(
        sa.text("SELECT user_id, memory_text FROM memory WHERE id = 20"),
    ).fetchone()
    if row:
        user_id, text = row[0], row[1]
        # Assign original to Brick
        conn.execute(sa.text(
            "UPDATE memory SET persona_id = 2 WHERE id = 20"
        ))
        # Copy for Haugen
        conn.execute(
            sa.text(
                "INSERT INTO memory (user_id, persona_id, memory_text) "
                "VALUES (:uid, 5, :txt)"
            ),
            {"uid": str(user_id), "txt": text},
        )

    # Step 4: Delete Meldrey's diagnostic memories and any remaining orphans
    conn.execute(sa.text(
        "DELETE FROM memory WHERE persona_id IS NULL"
    ))


def downgrade() -> None:
    op.drop_index("ix_memory_user_persona", table_name="memory")
    op.drop_constraint("memory_persona_id_fkey", "memory", type_="foreignkey")
    op.drop_column("memory", "persona_id")
