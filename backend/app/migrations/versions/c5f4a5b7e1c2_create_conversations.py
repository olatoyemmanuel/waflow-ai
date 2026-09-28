"""
Create conversations table.

A Conversation represents a tenant-owned communication thread between a
business and one customer.

Revision ID: c5f4a5b7e1c2
Revises: 81412bbd7d59
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic revision identifiers.
revision = "c5f4a5b7e1c2"
down_revision = "81412bbd7d59"
branch_labels = None
depends_on = None


# PostgreSQL enum definitions.
#
# create_type=False is critical here.
#
# The migration explicitly creates these enum types in upgrade(). Without
# create_type=False, SQLAlchemy's PostgreSQL ENUM implementation will also
# attempt to create the enum automatically when op.create_table() executes.
# That would cause PostgreSQL DuplicateObject errors.
conversation_channel_enum = postgresql.ENUM(
    "whatsapp",
    name="conversation_channel",
    create_type=False,
)

conversation_status_enum = postgresql.ENUM(
    "open",
    "pending",
    "resolved",
    "closed",
    name="conversation_status",
    create_type=False,
)

conversation_handling_mode_enum = postgresql.ENUM(
    "ai",
    "human",
    name="conversation_handling_mode",
    create_type=False,
)


def upgrade() -> None:
    """
    Create PostgreSQL enum types, the conversations table, and indexes.
    """

    bind = op.get_bind()

    # Create each PostgreSQL enum exactly once before the table is created.
    conversation_channel_enum.create(
        bind,
        checkfirst=True,
    )

    conversation_status_enum.create(
        bind,
        checkfirst=True,
    )

    conversation_handling_mode_enum.create(
        bind,
        checkfirst=True,
    )

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "assigned_user_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "channel",
            conversation_channel_enum,
            nullable=False,
        ),
        sa.Column(
            "status",
            conversation_status_enum,
            nullable=False,
        ),
        sa.Column(
            "handling_mode",
            conversation_handling_mode_enum,
            nullable=False,
        ),
        sa.Column(
            "unread_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_conversations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_conversations_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            name="fk_conversations_assigned_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_conversations",
        ),
    )

    # Shared-database tenant-scoped indexes.
    #
    # These match the query patterns expected by the future shared inbox,
    # conversation filtering, assignment, and ordering operations.

    op.create_index(
        "ix_conversations_tenant_id",
        "conversations",
        ["tenant_id"],
    )

    op.create_index(
        "ix_conversations_tenant_status",
        "conversations",
        ["tenant_id", "status"],
    )

    op.create_index(
        "ix_conversations_tenant_channel",
        "conversations",
        ["tenant_id", "channel"],
    )

    op.create_index(
        "ix_conversations_tenant_handling_mode",
        "conversations",
        ["tenant_id", "handling_mode"],
    )

    op.create_index(
        "ix_conversations_tenant_customer",
        "conversations",
        ["tenant_id", "customer_id"],
    )

    op.create_index(
        "ix_conversations_tenant_assigned_user",
        "conversations",
        ["tenant_id", "assigned_user_id"],
    )

    op.create_index(
        "ix_conversations_tenant_last_message_at",
        "conversations",
        ["tenant_id", "last_message_at"],
    )

    op.create_index(
        "ix_conversations_tenant_created_at",
        "conversations",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    """
    Drop the conversations table, indexes, and PostgreSQL enum types.
    """

    bind = op.get_bind()

    # Drop indexes before the table.
    op.drop_index(
        "ix_conversations_tenant_created_at",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_last_message_at",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_assigned_user",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_customer",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_handling_mode",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_channel",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_status",
        table_name="conversations",
    )

    op.drop_index(
        "ix_conversations_tenant_id",
        table_name="conversations",
    )

    op.drop_table(
        "conversations",
    )

    # Drop PostgreSQL enum types only after the dependent table is gone.
    conversation_handling_mode_enum.drop(
        bind,
        checkfirst=True,
    )

    conversation_status_enum.drop(
        bind,
        checkfirst=True,
    )

    conversation_channel_enum.drop(
        bind,
        checkfirst=True,
    )