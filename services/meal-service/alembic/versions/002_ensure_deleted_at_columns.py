"""Ensure deleted_at exists on meals/people in meal and public schemas.

Revision ID: 002_ensure_deleted_at
Revises: 001_soft_delete
Create Date: 2026-06-10

Production may have created tables in public before schema binding; use
idempotent ALTERs on both schemas.
"""
from __future__ import annotations

from alembic import op

revision = "002_ensure_deleted_at"
down_revision = "001_soft_delete"
branch_labels = None
depends_on = None


def _add_deleted_at(schema: str, table: str) -> None:
    op.execute(
        f"""
        DO $$ BEGIN
            ALTER TABLE "{schema}".{table}
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
            CREATE INDEX IF NOT EXISTS ix_{table}_deleted_at
                ON "{schema}".{table} (deleted_at);
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )


def upgrade() -> None:
    for schema in ("meal", "public"):
        _add_deleted_at(schema, "meals")
        _add_deleted_at(schema, "people")
    for schema in ("meal", "public"):
        op.execute(
            f"""
            DO $$ BEGIN
                UPDATE "{schema}".people
                SET deleted_at = updated_at
                WHERE is_removed = true AND deleted_at IS NULL;
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
            """
        )


def downgrade() -> None:
    for schema in ("meal", "public"):
        op.execute(f'DROP INDEX IF EXISTS "{schema}".ix_meals_deleted_at')
        op.execute(
            f'ALTER TABLE IF EXISTS "{schema}".meals DROP COLUMN IF EXISTS deleted_at'
        )
        op.execute(f'DROP INDEX IF EXISTS "{schema}".ix_people_deleted_at')
        op.execute(
            f'ALTER TABLE IF EXISTS "{schema}".people DROP COLUMN IF EXISTS deleted_at'
        )
