"""
Conversation domain model tests.

These tests verify the model metadata and domain-level defaults before
the database migration is introduced.
"""

import uuid

from sqlalchemy import inspect

from app.modules.conversations.models import (
    Conversation,
    ConversationChannel,
    ConversationHandlingMode,
    ConversationStatus,
)


def test_conversation_table_name() -> None:
    """The Conversation model maps to the conversations table."""

    assert Conversation.__tablename__ == "conversations"


def test_conversation_has_uuid_primary_key() -> None:
    """Conversation IDs use UUID values."""

    conversation = Conversation()

    assert conversation.id is None or isinstance(
        conversation.id,
        uuid.UUID,
    )

    primary_key_columns = [
        column
        for column in inspect(Conversation).columns
        if column.primary_key
    ]

    assert len(primary_key_columns) == 1
    assert primary_key_columns[0].name == "id"


def test_conversation_has_required_tenant_and_customer_fields() -> None:
    """Tenant and customer ownership fields are mandatory."""

    mapper = inspect(Conversation)

    tenant_column = mapper.columns.tenant_id
    customer_column = mapper.columns.customer_id

    assert tenant_column.nullable is False
    assert customer_column.nullable is False


def test_conversation_has_optional_assignment() -> None:
    """Human assignment is optional."""

    assigned_user_column = inspect(
        Conversation,
    ).columns.assigned_user_id

    assert assigned_user_column.nullable is True


def test_conversation_enum_values() -> None:
    """Conversation enums expose the expected persisted values."""

    assert ConversationChannel.WHATSAPP.value == "whatsapp"

    assert {
        status.value
        for status in ConversationStatus
    } == {
        "open",
        "pending",
        "resolved",
        "closed",
    }

    assert {
        mode.value
        for mode in ConversationHandlingMode
    } == {
        "ai",
        "human",
    }


def test_conversation_enum_defaults_are_defined() -> None:
    """Database columns define explicit lifecycle defaults."""

    mapper = inspect(Conversation)

    channel_column = mapper.columns.channel
    status_column = mapper.columns.status
    handling_mode_column = mapper.columns.handling_mode
    unread_count_column = mapper.columns.unread_count

    assert channel_column.default is not None
    assert status_column.default is not None
    assert handling_mode_column.default is not None
    assert unread_count_column.default is not None


def test_conversation_unread_count_is_non_nullable() -> None:
    """Unread count cannot be NULL."""

    column = inspect(
        Conversation,
    ).columns.unread_count

    assert column.nullable is False


def test_conversation_indexes_are_tenant_scoped() -> None:
    """
    Inbox-oriented indexes must include tenant_id.

    This protects the intended query pattern for a shared PostgreSQL
    database where all tenants coexist in the same physical database.
    """

    indexes = {
        index.name: {
            column.name
            for column in index.columns
        }
        for index in Conversation.__table__.indexes
    }

    expected_indexes = {
        "ix_conversations_tenant_status",
        "ix_conversations_tenant_channel",
        "ix_conversations_tenant_handling_mode",
        "ix_conversations_tenant_customer",
        "ix_conversations_tenant_assigned_user",
        "ix_conversations_tenant_last_message_at",
        "ix_conversations_tenant_created_at",
    }

    assert expected_indexes.issubset(indexes.keys())

    for index_name in expected_indexes:
        assert "tenant_id" in indexes[index_name]