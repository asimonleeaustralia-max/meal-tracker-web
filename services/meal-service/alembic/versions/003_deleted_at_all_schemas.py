"""Add deleted_at to every meals/people table regardless of schema.

Revision ID: 003_deleted_at_all
Revises: 002_ensure_deleted_at
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op

revision = "003_deleted_at_all"
down_revision = "002_ensure_deleted_at"
branch_labels = None
depends_on = None


def _add_column_everywhere(table: str) -> None:
    op.execute(
        f"""
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name = '{table}'
                  AND table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.{table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ',
                    r.table_schema
                );
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS ix_{table}_deleted_at ON %I.{table} (deleted_at)',
                    r.table_schema
                );
            END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    _add_column_everywhere("meals")
    _add_column_everywhere("people")
    op.execute(
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name = 'people'
                  AND table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            LOOP
                EXECUTE format(
                    'UPDATE %I.people SET deleted_at = updated_at '
                    'WHERE is_removed = true AND deleted_at IS NULL',
                    r.table_schema
                );
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name IN ('meals', 'people')
                  AND table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            LOOP
                EXECUTE format(
                    'DROP INDEX IF EXISTS %I.ix_%s_deleted_at',
                    r.table_schema, r.table_name
                );
                EXECUTE format(
                    'ALTER TABLE %I.%I DROP COLUMN IF EXISTS deleted_at',
                    r.table_schema, r.table_name
                );
            END LOOP;
        END $$;
        """
    )
