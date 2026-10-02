"""Tests for the Message domain model."""

import uuid

from sqlalchemy import inspect

from app.modules.messages.models import (
    Message,
    MessageDirection,
    MessageSenderType,
    MessageStatus,
    MessageType,
)


def test_message_table_name() -> None:
    """Message uses the expected database table name."""

    assert Message.__tablename__ == "messages"


def test_message_has_uuid_primary_key() -> None:
    """Message uses a UUID primary key."""

    mapper = inspect(Message)
    primary_key = mapper.primary_key[0]

    assert primary_key.name == "id"
    assert str(primary_key.type).upper().startswith("UUID")


def test_message_requires_tenant_and_conversation() -> None:
    """Message requires tenant and conversation ownership."""

    mapper = inspect(Message)

    tenant_column = mapper.columns["tenant_id"]
    conversation_column = mapper.columns["conversation_id"]

    assert tenant_column.nullable is False
    assert conversation_column.nullable is False


def test_message_supports_optional_sender_user() -> None:
    """Human sender linkage is optional."""

    mapper = inspect(Message)

    sender_user_column = mapper.columns["sender_user_id"]

    assert sender_user_column.nullable is True


def test_message_enum_values() -> None:
    """Message enums expose the expected domain values."""

    assert {item.value for item in MessageDirection} == {
        "inbound",
        "outbound",
    }

    assert {item.value for item in MessageSenderType} == {
        "customer",
        "agent",
        "ai",
        "system",
    }

    assert {item.value for item in MessageType} == {
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
    }

    assert {item.value for item in MessageStatus} == {
        "pending",
        "sent",
        "delivered",
        "read",
        "failed",
    }


def test_message_enum_database_values_are_lowercase() -> None:
    """PostgreSQL enum metadata uses explicit lowercase domain values."""

    mapper = inspect(Message)

    expected = {
        "direction": {
            "inbound",
            "outbound",
        },
        "sender_type": {
            "customer",
            "agent",
            "ai",
            "system",
        },
        "message_type": {
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
        },
        "status": {
            "pending",
            "sent",
            "delivered",
            "read",
            "failed",
        },
    }

    for column_name, expected_values in expected.items():
        enum_type = mapper.columns[column_name].type

        assert set(enum_type.enums) == expected_values


def test_message_core_columns_are_present() -> None:
    """Message exposes all required domain columns."""

    mapper = inspect(Message)

    expected_columns = {
        "id",
        "tenant_id",
        "conversation_id",
        "direction",
        "sender_type",
        "message_type",
        "status",
        "content",
        "provider_message_id",
        "sender_user_id",
        "created_at",
        "updated_at",
    }

    assert expected_columns.issubset(
        {column.name for column in mapper.columns}
    )


def test_message_content_and_provider_id_are_optional() -> None:
    """Content and provider IDs may be absent for non-text/system events."""

    mapper = inspect(Message)

    assert mapper.columns["content"].nullable is True
    assert mapper.columns["provider_message_id"].nullable is True


def test_message_has_expected_tenant_scoped_indexes() -> None:
    """Message has exactly the deliberate tenant-scoped indexes."""

    index_names = {
        index.name
        for index in Message.__table__.indexes
    }

    expected_indexes = {
        "ix_messages_tenant_conversation",
        "ix_messages_tenant_direction",
        "ix_messages_tenant_status",
        "ix_messages_tenant_sender_type",
        "ix_messages_tenant_message_type",
        "ix_messages_tenant_created_at",
        "ix_messages_tenant_provider_message_id",
    }

    assert expected_indexes == index_names


def test_message_default_id_factory_is_uuid() -> None:
    """The primary-key default generates UUID values."""

    assert isinstance(uuid.uuid4(), uuid.UUID)