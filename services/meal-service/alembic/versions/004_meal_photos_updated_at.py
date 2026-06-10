"""Add updated_at to meal_photos in every schema.

Revision ID: 004_meal_photos_updated_at
Revises: 003_deleted_at_all
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op

revision = "004_meal_photos_updated_at"
down_revision = "003_deleted_at_all"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name = 'meal_photos'
                  AND table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.meal_photos '
                    'ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()',
                    r.table_schema
                );
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS ix_meal_photos_updated_at '
                    'ON %I.meal_photos (updated_at)',
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
                WHERE table_name = 'meal_photos'
                  AND table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            LOOP
                EXECUTE format(
                    'DROP INDEX IF EXISTS %I.ix_meal_photos_updated_at',
                    r.table_schema
                );
                EXECUTE format(
                    'ALTER TABLE %I.meal_photos DROP COLUMN IF EXISTS updated_at',
                    r.table_schema
                );
            END LOOP;
        END $$;
        """
    )
