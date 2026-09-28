"""
WAFlow AI conversation domain model.

A Conversation represents a customer communication thread within a
tenant. The initial implementation is channel-aware and designed around
WhatsApp.

Security principles:

- Every conversation belongs to exactly one tenant.
- Every conversation is associated with exactly one customer.
- Tenant ownership is enforced by the application/service layer.
- Database foreign keys protect referenced records.
- Assignment to a user is optional.
- Conversation lifecycle changes are explicit through status values.
- AI versus human handling is represented explicitly.
- PostgreSQL timezone-aware timestamps are used explicitly so the ORM
  metadata matches the PostgreSQL schema used by Alembic.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class ConversationChannel(str, enum.Enum):
    """
    Communication channel used by a conversation.

    WhatsApp is the first supported channel for WAFlow AI. Additional
    channels can be added later without redesigning the Conversation
    aggregate.
    """

    WHATSAPP = "whatsapp"


class ConversationStatus(str, enum.Enum):
    """
    Conversation lifecycle state.

    OPEN:
        Conversation requires active attention.

    PENDING:
        Conversation is waiting for a customer, external system, or
        another action before it can continue.

    RESOLVED:
        The customer request has been resolved but the conversation
        remains available for historical reference.

    CLOSED:
        Conversation has been explicitly closed.
    """

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationHandlingMode(str, enum.Enum):
    """
    Current handler for a conversation.

    AI:
        The AI automation layer is responsible for handling the
        conversation.

    HUMAN:
        A human agent is responsible for handling the conversation.
    """

    AI = "ai"
    HUMAN = "human"


class Conversation(Base):
    """
    Tenant-owned customer conversation.

    A conversation belongs to one tenant and one customer. It may
    optionally be assigned to a user who belongs to that tenant.

    Message records will reference this model through conversation_id.
    """

    __tablename__ = "conversations"

    __table_args__ = (
        Index(
            "ix_conversations_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_conversations_tenant_channel",
            "tenant_id",
            "channel",
        ),
        Index(
            "ix_conversations_tenant_handling_mode",
            "tenant_id",
            "handling_mode",
        ),
        Index(
            "ix_conversations_tenant_customer",
            "tenant_id",
            "customer_id",
        ),
        Index(
            "ix_conversations_tenant_assigned_user",
            "tenant_id",
            "assigned_user_id",
        ),
        Index(
            "ix_conversations_tenant_last_message_at",
            "tenant_id",
            "last_message_at",
        ),
        Index(
            "ix_conversations_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "customers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    channel: Mapped[ConversationChannel] = mapped_column(
        SqlEnum(
            ConversationChannel,
            name="conversation_channel",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=ConversationChannel.WHATSAPP,
    )

    status: Mapped[ConversationStatus] = mapped_column(
        SqlEnum(
            ConversationStatus,
            name="conversation_status",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=ConversationStatus.OPEN,
    )

    handling_mode: Mapped[ConversationHandlingMode] = mapped_column(
        SqlEnum(
            ConversationHandlingMode,
            name="conversation_handling_mode",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=ConversationHandlingMode.AI,
    )

    unread_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    last_message_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )