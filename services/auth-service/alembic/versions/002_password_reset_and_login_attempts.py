"""Add login_attempts and password_reset_tokens tables.

Revision ID: 002_password_reset
Revises: 001_activity_logging
Create Date: 2026-06-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_password_reset"
down_revision = "001_activity_logging"
branch_labels = None
depends_on = None

SCHEMA = "auth"


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempts_email",
        "login_attempts",
        ["email"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempts_ip_address",
        "login_attempts",
        ["ip_address"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempts_failed_at",
        "login_attempts",
        ["failed_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_token_hash"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens", schema=SCHEMA)
    op.drop_table("login_attempts", schema=SCHEMA)
