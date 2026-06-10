"""Add deleted_at soft-delete tombstone columns to meals and people.

Revision ID: 001_soft_delete
Revises:
Create Date: 2026-06-10

Soft-delete strategy: in-place tombstones. DELETE /meals/{id} sets deleted_at
instead of removing the row so incremental sync (?since=) can propagate deletes.
People tombstones also set deleted_at when is_removed=true via PUT.
"""
from __future__ import annotations

from alembic import op

revision = "001_soft_delete"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "meal"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    op.execute(
        f"""
        DO $$ BEGIN
            ALTER TABLE "{SCHEMA}".meals
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
            CREATE INDEX IF NOT EXISTS ix_meals_deleted_at
                ON "{SCHEMA}".meals (deleted_at);
            ALTER TABLE "{SCHEMA}".people
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
            CREATE INDEX IF NOT EXISTS ix_people_deleted_at
                ON "{SCHEMA}".people (deleted_at);
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )
    op.execute(
        f'UPDATE "{SCHEMA}".people '
        "SET deleted_at = updated_at "
        "WHERE is_removed = true AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_people_deleted_at", table_name="people", schema=SCHEMA)
    op.drop_column("people", "deleted_at", schema=SCHEMA)
    op.drop_index("ix_meals_deleted_at", table_name="meals", schema=SCHEMA)
    op.drop_column("meals", "deleted_at", schema=SCHEMA)
