"""
Tests for the WAFlow AI MessageService.

These tests focus on:

- tenant-context enforcement
- conversation tenant validation
- message creation
- tenant-scoped retrieval
- provider message ID handling
- conversation message access
- message filtering
- message mutation
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services import TenantContext
from app.modules.messages.models import (
    Message,
    MessageDirection,
    MessageSenderType,
    MessageStatus,
    MessageType,
)
from app.modules.messages.service import MessageService


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def other_tenant_id():
    return uuid4()


@pytest.fixture
def tenant_context(tenant_id):
    return TenantContext(
        user_id=uuid4(),
        membership_id=uuid4(),
        tenant_id=tenant_id,
        role_id=uuid4(),
        role_name="OWNER",
    )


@pytest.fixture
def repository(tenant_id):
    repository = AsyncMock()
    repository.tenant_id = tenant_id
    repository.db = AsyncMock()
    return repository


@pytest.fixture
def conversation_repository(tenant_id):
    repository = AsyncMock()
    repository.tenant_id = tenant_id
    return repository


@pytest.fixture
def service(
    repository,
    conversation_repository,
    tenant_context,
):
    return MessageService(
        repository=repository,
        conversation_repository=conversation_repository,
        tenant_context=tenant_context,
    )


@pytest.fixture
def conversation():
    return type(
        "ConversationStub",
        (),
        {
            "id": uuid4(),
        },
    )()


@pytest.fixture
def message(tenant_id, conversation):
    return Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        sender_user_id=None,
        direction=MessageDirection.INBOUND,
        sender_type=MessageSenderType.CUSTOMER,
        message_type=MessageType.TEXT,
        status=MessageStatus.PENDING,
        content="Hello",
        provider_message_id=None,
    )


def test_service_requires_matching_conversation_repository_tenant(
    repository,
    conversation_repository,
    tenant_context,
    other_tenant_id,
):
    conversation_repository.tenant_id = other_tenant_id

    with pytest.raises(
        ValueError,
        match="Conversation repository tenant does not match",
    ):
        MessageService(
            repository=repository,
            conversation_repository=conversation_repository,
            tenant_context=tenant_context,
        )


@pytest.mark.asyncio
async def test_create_validates_conversation(
    service,
    conversation_repository,
    repository,
    conversation,
):
    conversation_repository.get_by_id.return_value = conversation

    repository.get_by_provider_message_id.return_value = None

    result = await service.create(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender_type=MessageSenderType.CUSTOMER,
        content="Hello",
    )

    conversation_repository.get_by_id.assert_awaited_once_with(
        conversation.id,
    )
    repository.add.assert_awaited_once()
    repository.db.refresh.assert_awaited_once()

    assert result.conversation_id == conversation.id


@pytest.mark.asyncio
async def test_create_derives_tenant_from_context(
    service,
    tenant_context,
    conversation_repository,
    repository,
    conversation,
):
    conversation_repository.get_by_id.return_value = conversation
    repository.get_by_provider_message_id.return_value = None

    result = await service.create(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_type=MessageSenderType.AI,
        content="Welcome!",
    )

    assert result.tenant_id == tenant_context.tenant_id


@pytest.mark.asyncio
async def test_create_rejects_unknown_conversation(
    service,
    conversation_repository,
    repository,
):
    conversation_id = uuid4()
    conversation_repository.get_by_id.return_value = None

    with pytest.raises(
        ValueError,
        match="Conversation does not exist in the current tenant",
    ):
        await service.create(
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND,
            sender_type=MessageSenderType.CUSTOMER,
            content="Hello",
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_provider_message_id(
    service,
    conversation_repository,
    repository,
    conversation,
    message,
):
    conversation_repository.get_by_id.return_value = conversation
    repository.get_by_provider_message_id.return_value = message

    with pytest.raises(
        ValueError,
        match="provider_message_id already exists",
    ):
        await service.create(
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            sender_type=MessageSenderType.CUSTOMER,
            provider_message_id="provider-123",
        )

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_delegates_to_tenant_scoped_repository(
    service,
    repository,
    message,
):
    repository.get_by_id.return_value = message

    result = await service.get(message.id)

    repository.get_by_id.assert_awaited_once_with(message.id)
    assert result is message


@pytest.mark.asyncio
async def test_get_by_provider_message_id(
    service,
    repository,
    message,
):
    repository.get_by_provider_message_id.return_value = message

    result = await service.get_by_provider_message_id(
        "provider-123",
    )

    repository.get_by_provider_message_id.assert_awaited_once_with(
        "provider-123",
    )
    assert result is message


@pytest.mark.asyncio
async def test_list_by_conversation_validates_conversation(
    service,
    conversation_repository,
    repository,
    conversation,
):
    conversation_repository.get_by_id.return_value = conversation
    repository.list_by_conversation.return_value = []

    result = await service.list_by_conversation(
        conversation.id,
    )

    conversation_repository.get_by_id.assert_awaited_once_with(
        conversation.id,
    )
    repository.list_by_conversation.assert_awaited_once_with(
        conversation.id,
    )
    assert result == []


@pytest.mark.asyncio
async def test_list_by_conversation_returns_empty_for_unknown_conversation(
    service,
    conversation_repository,
    repository,
):
    conversation_id = uuid4()
    conversation_repository.get_by_id.return_value = None

    result = await service.list_by_conversation(conversation_id)

    assert result == []
    repository.list_by_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_count_by_conversation_returns_zero_for_unknown_conversation(
    service,
    conversation_repository,
    repository,
):
    conversation_id = uuid4()
    conversation_repository.get_by_id.return_value = None

    result = await service.count_by_conversation(conversation_id)

    assert result == 0
    repository.count_by_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_by_direction(
    service,
    repository,
    message,
):
    repository.list_by_direction.return_value = [message]

    result = await service.list_by_direction(
        MessageDirection.INBOUND,
    )

    repository.list_by_direction.assert_awaited_once_with(
        MessageDirection.INBOUND,
    )
    assert result == [message]


@pytest.mark.asyncio
async def test_count_by_direction(
    service,
    repository,
):
    repository.count_by_direction.return_value = 4

    result = await service.count_by_direction(
        MessageDirection.INBOUND,
    )

    assert result == 4


@pytest.mark.asyncio
async def test_list_by_sender_type(
    service,
    repository,
    message,
):
    repository.list_by_sender_type.return_value = [message]

    result = await service.list_by_sender_type(
        MessageSenderType.CUSTOMER,
    )

    repository.list_by_sender_type.assert_awaited_once_with(
        MessageSenderType.CUSTOMER,
    )
    assert result == [message]


@pytest.mark.asyncio
async def test_count_by_sender_type(
    service,
    repository,
):
    repository.count_by_sender_type.return_value = 7

    result = await service.count_by_sender_type(
        MessageSenderType.AI,
    )

    assert result == 7


@pytest.mark.asyncio
async def test_list_by_message_type(
    service,
    repository,
    message,
):
    repository.list_by_message_type.return_value = [message]

    result = await service.list_by_message_type(
        MessageType.TEXT,
    )

    repository.list_by_message_type.assert_awaited_once_with(
        MessageType.TEXT,
    )
    assert result == [message]


@pytest.mark.asyncio
async def test_count_by_message_type(
    service,
    repository,
):
    repository.count_by_message_type.return_value = 8

    result = await service.count_by_message_type(
        MessageType.TEXT,
    )

    assert result == 8


@pytest.mark.asyncio
async def test_list_by_status(
    service,
    repository,
    message,
):
    repository.list_by_status.return_value = [message]

    result = await service.list_by_status(
        MessageStatus.PENDING,
    )

    repository.list_by_status.assert_awaited_once_with(
        MessageStatus.PENDING,
    )
    assert result == [message]


@pytest.mark.asyncio
async def test_count_by_status(
    service,
    repository,
):
    repository.count_by_status.return_value = 3

    result = await service.count_by_status(
        MessageStatus.SENT,
    )

    assert result == 3


@pytest.mark.asyncio
async def test_change_status(
    service,
    repository,
    message,
):
    repository.get_by_id.return_value = message

    result = await service.change_status(
        message.id,
        MessageStatus.DELIVERED,
    )

    assert result.status == MessageStatus.DELIVERED
    repository.db.flush.assert_awaited_once()
    repository.db.refresh.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_change_status_rejects_unknown_message(
    service,
    repository,
):
    message_id = uuid4()
    repository.get_by_id.return_value = None

    with pytest.raises(
        ValueError,
        match="Message does not exist in the current tenant",
    ):
        await service.change_status(
            message_id,
            MessageStatus.SENT,
        )

    repository.db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_content(
    service,
    repository,
    message,
):
    repository.get_by_id.return_value = message

    result = await service.update_content(
        message.id,
        "Updated content",
    )

    assert result.content == "Updated content"
    repository.db.flush.assert_awaited_once()
    repository.db.refresh.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_update_provider_message_id(
    service,
    repository,
    message,
):
    repository.get_by_id.return_value = message
    repository.get_by_provider_message_id.return_value = None

    result = await service.update_provider_message_id(
        message.id,
        "provider-456",
    )

    assert result.provider_message_id == "provider-456"
    repository.db.flush.assert_awaited_once()
    repository.db.refresh.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_update_provider_message_id_rejects_duplicate(
    service,
    repository,
    message,
):
    other_message = Message(
        id=uuid4(),
        tenant_id=message.tenant_id,
        conversation_id=message.conversation_id,
        direction=MessageDirection.INBOUND,
        sender_type=MessageSenderType.CUSTOMER,
        message_type=MessageType.TEXT,
        status=MessageStatus.SENT,
        content="Other message",
        provider_message_id="provider-999",
    )

    repository.get_by_id.return_value = message
    repository.get_by_provider_message_id.return_value = other_message

    with pytest.raises(
        ValueError,
        match="provider_message_id already exists",
    ):
        await service.update_provider_message_id(
            message.id,
            "provider-999",
        )

    repository.db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_provider_message_id_allows_current_value(
    service,
    repository,
    message,
):
    message.provider_message_id = "provider-current"

    repository.get_by_id.return_value = message
    repository.get_by_provider_message_id.return_value = message

    result = await service.update_provider_message_id(
        message.id,
        "provider-current",
    )

    assert result.provider_message_id == "provider-current"
    repository.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_last_message_timestamp(
    service,
    repository,
    message,
):
    repository.get_by_id.return_value = message

    timestamp = datetime(
        2026,
        10,
        2,
        12,
        30,
        tzinfo=timezone.utc,
    )

    result = await service.update_last_message_timestamp(
        message.id,
        timestamp,
    )

    assert result.created_at == timestamp
    repository.db.flush.assert_awaited_once()
    repository.db.refresh.assert_awaited_once_with(message)