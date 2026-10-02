"""
WAFlow AI message domain model.

A Message represents one communication event inside a Conversation.

The model is intentionally provider-agnostic at the domain level while
supporting the message types and delivery states required by the initial
WhatsApp integration.

Security principles:

- Every message belongs to exactly one tenant.
- Every message belongs to exactly one conversation.
- Tenant ownership is derived from the authenticated tenant context.
- Provider identifiers are stored for idempotency and webhook correlation.
- Sender classification explicitly distinguishes customers, agents, AI,
  and system-generated messages.
- Message lifecycle is represented explicitly through status values.
- PostgreSQL enums persist the explicit lowercase domain values.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class MessageDirection(str, enum.Enum):
    """Direction in which a message travels."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageSenderType(str, enum.Enum):
    """Actor responsible for producing a message."""

    CUSTOMER = "customer"
    AGENT = "agent"
    AI = "ai"
    SYSTEM = "system"


class MessageType(str, enum.Enum):
    """Supported message content types."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    INTERACTIVE = "interactive"
    TEMPLATE = "template"
    UNKNOWN = "unknown"


class MessageStatus(str, enum.Enum):
    """Message delivery lifecycle."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


def _enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """
    Return explicit enum values for PostgreSQL persistence.

    SQLAlchemy otherwise uses Python enum member names by default. WAFlow AI
    uses the lowercase values as the stable database/domain representation.
    """

    return [member.value for member in enum_class]


class Message(Base):
    """
    Tenant-owned message belonging to one conversation.

    A message can originate from the customer, a human agent, the AI
    assistant, or the system. Direction and sender type are kept separately
    because they represent different domain concepts.
    """

    __tablename__ = "messages"

    __table_args__ = (
        Index(
            "ix_messages_tenant_conversation",
            "tenant_id",
            "conversation_id",
        ),
        Index(
            "ix_messages_tenant_direction",
            "tenant_id",
            "direction",
        ),
        Index(
            "ix_messages_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_messages_tenant_sender_type",
            "tenant_id",
            "sender_type",
        ),
        Index(
            "ix_messages_tenant_message_type",
            "tenant_id",
            "message_type",
        ),
        Index(
            "ix_messages_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_messages_tenant_provider_message_id",
            "tenant_id",
            "provider_message_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    direction: Mapped[MessageDirection] = mapped_column(
        postgresql.ENUM(
            MessageDirection,
            name="message_direction",
            values_callable=_enum_values,
            create_type=True,
        ),
        nullable=False,
    )

    sender_type: Mapped[MessageSenderType] = mapped_column(
        postgresql.ENUM(
            MessageSenderType,
            name="message_sender_type",
            values_callable=_enum_values,
            create_type=True,
        ),
        nullable=False,
    )

    message_type: Mapped[MessageType] = mapped_column(
        postgresql.ENUM(
            MessageType,
            name="message_type",
            values_callable=_enum_values,
            create_type=True,
        ),
        nullable=False,
    )

    status: Mapped[MessageStatus] = mapped_column(
        postgresql.ENUM(
            MessageStatus,
            name="message_status",
            values_callable=_enum_values,
            create_type=True,
        ),
        nullable=False,
    )

    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
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