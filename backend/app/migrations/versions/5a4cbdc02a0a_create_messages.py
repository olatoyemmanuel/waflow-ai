"""
Create messages table.

A Message represents one communication event inside a Conversation.

Revision ID: 5a4cbdc02a0a
Revises: c5f4a5b7e1c2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic revision identifiers.
revision = "5a4cbdc02a0a"
down_revision = "c5f4a5b7e1c2"
branch_labels = None
depends_on = None


# PostgreSQL enums are created explicitly in upgrade().
#
# create_type=False prevents SQLAlchemy from attempting to create these
# enum types a second time when the messages table is created.
message_direction_enum = postgresql.ENUM(
    "inbound",
    "outbound",
    name="message_direction",
    create_type=False,
)

message_sender_type_enum = postgresql.ENUM(
    "customer",
    "agent",
    "ai",
    "system",
    name="message_sender_type",
    create_type=False,
)

message_type_enum = postgresql.ENUM(
    "text",
    "image",
    "audio",
    "video",
    "document",
    "sticker",
    "location",
    "interactive",
    "template",
    "unknown",
    name="message_type",
    create_type=False,
)

message_status_enum = postgresql.ENUM(
    "pending",
    "sent",
    "delivered",
    "read",
    "failed",
    name="message_status",
    create_type=False,
)


def upgrade() -> None:
    """Create PostgreSQL message enums, messages table, and indexes."""

    bind = op.get_bind()

    # Create each PostgreSQL enum explicitly before creating the table.
    message_direction_enum.create(bind, checkfirst=True)
    message_sender_type_enum.create(bind, checkfirst=True)
    message_type_enum.create(bind, checkfirst=True)
    message_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "direction",
            message_direction_enum,
            nullable=False,
        ),
        sa.Column(
            "sender_type",
            message_sender_type_enum,
            nullable=False,
        ),
        sa.Column(
            "message_type",
            message_type_enum,
            nullable=False,
        ),
        sa.Column(
            "status",
            message_status_enum,
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "provider_message_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "sender_user_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_messages_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name="fk_messages_sender_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_messages",
        ),
    )

    # Deliberate tenant-scoped indexes.
    #
    # We intentionally do not create standalone indexes on tenant_id or
    # conversation_id. The composite tenant+conversation index covers the
    # primary tenant-scoped conversation lookup pattern.
    op.create_index(
        "ix_messages_tenant_conversation",
        "messages",
        ["tenant_id", "conversation_id"],
    )

    op.create_index(
        "ix_messages_tenant_direction",
        "messages",
        ["tenant_id", "direction"],
    )

    op.create_index(
        "ix_messages_tenant_status",
        "messages",
        ["tenant_id", "status"],
    )

    op.create_index(
        "ix_messages_tenant_sender_type",
        "messages",
        ["tenant_id", "sender_type"],
    )

    op.create_index(
        "ix_messages_tenant_message_type",
        "messages",
        ["tenant_id", "message_type"],
    )

    op.create_index(
        "ix_messages_tenant_created_at",
        "messages",
        ["tenant_id", "created_at"],
    )

    op.create_index(
        "ix_messages_tenant_provider_message_id",
        "messages",
        ["tenant_id", "provider_message_id"],
    )


def downgrade() -> None:
    """Drop messages indexes, table, and PostgreSQL enums."""

    bind = op.get_bind()

    # Drop indexes before the table.
    op.drop_index(
        "ix_messages_tenant_provider_message_id",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_created_at",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_message_type",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_sender_type",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_status",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_direction",
        table_name="messages",
    )

    op.drop_index(
        "ix_messages_tenant_conversation",
        table_name="messages",
    )

    op.drop_table("messages")

    # Drop enums after the table no longer references them.
    message_status_enum.drop(bind, checkfirst=True)
    message_type_enum.drop(bind, checkfirst=True)
    message_sender_type_enum.drop(bind, checkfirst=True)
    message_direction_enum.drop(bind, checkfirst=True)
