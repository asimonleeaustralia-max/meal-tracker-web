"""Add login_sessions and activity_events tables.

Revision ID: 001_activity_logging
Revises:
Create Date: 2026-06-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_activity_logging"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "auth"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    op.create_table(
        "login_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("login_method", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("client", sa.String(20), nullable=False, server_default="web"),
        sa.Column(
            "logged_in_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("logged_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_sessions_logged_in_at",
        "login_sessions",
        ["logged_in_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("path", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("bytes_saved", sa.BigInteger(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_activity_events_event_type",
        "activity_events",
        ["event_type"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_activity_events_created_at",
        "activity_events",
        ["created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("activity_events", schema=SCHEMA)
    op.drop_table("login_sessions", schema=SCHEMA)
