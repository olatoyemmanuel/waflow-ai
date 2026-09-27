"""
WAFlow AI refresh-session persistence model.

Refresh tokens are opaque random credentials.

Only their SHA-256 hashes are stored in PostgreSQL. A stolen database
therefore does not directly contain usable refresh tokens.

Each login starts a token family. Refresh-token rotation creates a new
session in the same family and marks the previous session as replaced.

If a previously revoked refresh token is presented again, the entire
token family is revoked. This provides refresh-token reuse detection.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class RefreshSession(Base):
    """
    Persistent refresh-token session.

    A session represents one refresh-token generation.

    Token lifecycle:

        active
          │
          └── refresh
                │
                ├── revoked_at set
                └── replaced_by_session_id set
    """

    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 digest of the opaque refresh token.
    # The plaintext token is returned only to the client.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    # All rotated tokens from one login belong to the same family.
    token_family_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        index=True,
    )

    # Session that replaced this session during rotation.
    replaced_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id"),
        nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Optional device/request metadata for future session management UI.
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )


# These indexes support the two most common security queries:
# 1. Find a refresh session by token hash.
# 2. Revoke all sessions belonging to a token family.
__table_args__ = (
    Index(
        "ix_refresh_sessions_family_revoked",
        "token_family_id",
        "revoked_at",
    ),
)
