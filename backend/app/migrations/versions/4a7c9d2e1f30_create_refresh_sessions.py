"""create refresh sessions

Revision ID: 4a7c9d2e1f30
Revises: 18f47d5b54a5
Create Date: 2026-09-27 05:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a7c9d2e1f30"
down_revision: str | Sequence[str] | None = "18f47d5b54a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent refresh-token sessions."""

    op.create_table(
        "refresh_sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "token_family_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "replaced_by_session_id",
            sa.Uuid(),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "ip_address",
            sa.String(length=64),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            ["refresh_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_refresh_sessions_token_hash",
        ),
    )

    op.create_index(
        "ix_refresh_sessions_user_id",
        "refresh_sessions",
        ["user_id"],
    )

    op.create_index(
        "ix_refresh_sessions_token_family_id",
        "refresh_sessions",
        ["token_family_id"],
    )

    op.create_index(
        "ix_refresh_sessions_expires_at",
        "refresh_sessions",
        ["expires_at"],
    )

    op.create_index(
        "ix_refresh_sessions_revoked_at",
        "refresh_sessions",
        ["revoked_at"],
    )

    op.create_index(
        "ix_refresh_sessions_family_revoked",
        "refresh_sessions",
        ["token_family_id", "revoked_at"],
    )


def downgrade() -> None:
    """Remove persistent refresh-token sessions."""

    op.drop_index(
        "ix_refresh_sessions_family_revoked",
        table_name="refresh_sessions",
    )

    op.drop_index(
        "ix_refresh_sessions_revoked_at",
        table_name="refresh_sessions",
    )

    op.drop_index(
        "ix_refresh_sessions_expires_at",
        table_name="refresh_sessions",
    )

    op.drop_index(
        "ix_refresh_sessions_token_family_id",
        table_name="refresh_sessions",
    )

    op.drop_index(
        "ix_refresh_sessions_user_id",
        table_name="refresh_sessions",
    )

    op.drop_table("refresh_sessions")
