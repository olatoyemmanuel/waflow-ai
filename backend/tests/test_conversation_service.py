"""
Tests for the tenant-scoped ConversationService.

These tests verify application-service behavior without coupling the
service tests to HTTP routes or database implementation details.

The test suite specifically covers:

- repository/context tenant-boundary validation
- customer tenant validation during creation
- tenant ownership derived from TenantContext
- conversation creation
- tenant-scoped reads
- filtered reads
- lifecycle mutations
- assignment and unassignment
- unread counter protection
- last-message timestamp updates
- database flush/refresh behavior
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.modules.auth.dependencies import TenantContext
from app.modules.conversations.models import (
    Conversation,
    ConversationChannel,
    ConversationHandlingMode,
    ConversationStatus,
)
from app.modules.conversations.service import ConversationService
from app.modules.customers.models import Customer


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Provide a deterministic tenant UUID for each test."""
    return uuid.uuid4()


@pytest.fixture
def other_tenant_id() -> uuid.UUID:
    """Provide a different tenant UUID for mismatch tests."""
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    """Provide a UUID representing the authenticated user."""
    return uuid.uuid4()


@pytest.fixture
def membership_id() -> uuid.UUID:
    """Provide a UUID representing the user's tenant membership."""
    return uuid.uuid4()


@pytest.fixture
def role_id() -> uuid.UUID:
    """Provide a UUID representing the user's role."""
    return uuid.uuid4()


@pytest.fixture
def customer_id() -> uuid.UUID:
    """Provide a customer UUID."""
    return uuid.uuid4()


@pytest.fixture
def conversation_id() -> uuid.UUID:
    """Provide a conversation UUID."""
    return uuid.uuid4()


@pytest.fixture
def assigned_user_id() -> uuid.UUID:
    """Provide an assigned-user UUID."""
    return uuid.uuid4()


@pytest.fixture
def tenant_context(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    membership_id: uuid.UUID,
    role_id: uuid.UUID,
) -> TenantContext:
    """
    Build the actual TenantContext used by the application.

    TenantContext represents the complete authenticated tenant context,
    not merely the tenant ID. The additional identity values are required
    because authorization has already resolved:

    - authenticated user
    - active membership
    - tenant
    - role
    """
    return TenantContext(
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        role_id=role_id,
        role_name="OWNER",
    )


@pytest.fixture
def repository(
    tenant_id: uuid.UUID,
) -> AsyncMock:
    """Provide a mocked ConversationRepository."""
    repository = AsyncMock()

    # The service relies on these attributes from the concrete repository.
    repository.tenant_id = tenant_id

    # TenantScopedRepository stores its AsyncSession as `db`.
    repository.db = AsyncMock()

    return repository


@pytest.fixture
def customer_repository(
    tenant_id: uuid.UUID,
) -> AsyncMock:
    """Provide a mocked CustomerRepository."""
    customer_repository = AsyncMock()
    customer_repository.tenant_id = tenant_id

    return customer_repository


@pytest.fixture
def service(
    repository: AsyncMock,
    customer_repository: AsyncMock,
    tenant_context: TenantContext,
) -> ConversationService:
    """Create a ConversationService bound to the test tenant."""
    return ConversationService(
        repository=repository,
        customer_repository=customer_repository,
        tenant_context=tenant_context,
    )


@pytest.fixture
def customer(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Customer:
    """Build a tenant-owned customer used by conversation tests."""
    return Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Test",
        last_name="Customer",
        phone="+2348000000000",
        email="customer@example.com",
    )


@pytest.fixture
def conversation(
    conversation_id: uuid.UUID,
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Conversation:
    """Build a tenant-owned conversation used by mutation tests."""
    return Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        channel=ConversationChannel.WHATSAPP,
        status=ConversationStatus.OPEN,
        handling_mode=ConversationHandlingMode.AI,
        unread_count=0,
    )


def test_service_accepts_matching_repository_tenants(
    service: ConversationService,
    tenant_id: uuid.UUID,
) -> None:
    """The service must preserve the authorized tenant boundary."""
    assert service.tenant_id == tenant_id
    assert service.repository.tenant_id == tenant_id
    assert service.customer_repository.tenant_id == tenant_id


def test_service_rejects_conversation_repository_tenant_mismatch(
    repository: AsyncMock,
    customer_repository: AsyncMock,
    tenant_context: TenantContext,
    other_tenant_id: uuid.UUID,
) -> None:
    """
    TenantScopedService must reject a conversation repository belonging
    to another tenant.
    """
    repository.tenant_id = other_tenant_id

    with pytest.raises(
        ValueError,
        match="Repository tenant does not match the tenant context",
    ):
        ConversationService(
            repository=repository,
            customer_repository=customer_repository,
            tenant_context=tenant_context,
        )


def test_service_rejects_customer_repository_tenant_mismatch(
    repository: AsyncMock,
    customer_repository: AsyncMock,
    tenant_context: TenantContext,
    other_tenant_id: uuid.UUID,
) -> None:
    """
    The conversation service must reject a customer repository belonging
    to another tenant.
    """
    customer_repository.tenant_id = other_tenant_id

    with pytest.raises(
        ValueError,
        match="Customer repository tenant does not match the tenant context",
    ):
        ConversationService(
            repository=repository,
            customer_repository=customer_repository,
            tenant_context=tenant_context,
        )


@pytest.mark.asyncio
async def test_create_rejects_customer_missing_from_authorized_tenant(
    service: ConversationService,
    customer_repository: AsyncMock,
    repository: AsyncMock,
    customer_id: uuid.UUID,
) -> None:
    """
    A conversation cannot be created when the customer is not visible
    through the tenant-scoped customer repository.
    """
    customer_repository.get_by_id.return_value = None

    with pytest.raises(
        ValueError,
        match="Customer does not exist in the authorized tenant",
    ):
        await service.create(
            customer_id,
        )

    customer_repository.get_by_id.assert_awaited_once_with(
        customer_id,
    )
    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_derives_tenant_from_tenant_context(
    service: ConversationService,
    customer_repository: AsyncMock,
    repository: AsyncMock,
    customer: Customer,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
) -> None:
    """
    Conversation creation must derive tenant_id from TenantContext rather
    than from caller input.
    """
    customer_repository.get_by_id.return_value = customer

    created_conversation = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        channel=ConversationChannel.WHATSAPP,
        status=ConversationStatus.OPEN,
        handling_mode=ConversationHandlingMode.AI,
        unread_count=0,
    )

    repository.add.return_value = created_conversation

    result = await service.create(
        customer_id,
    )

    assert result is created_conversation

    repository.add.assert_awaited_once()

    added_conversation = repository.add.await_args.args[0]

    assert isinstance(added_conversation, Conversation)
    assert added_conversation.tenant_id == tenant_id
    assert added_conversation.customer_id == customer_id
    assert added_conversation.channel == ConversationChannel.WHATSAPP
    assert added_conversation.status == ConversationStatus.OPEN
    assert added_conversation.handling_mode == ConversationHandlingMode.AI
    assert added_conversation.unread_count == 0


@pytest.mark.asyncio
async def test_create_supports_explicit_conversation_defaults(
    service: ConversationService,
    customer_repository: AsyncMock,
    repository: AsyncMock,
    customer: Customer,
) -> None:
    """Creation should preserve explicitly supplied lifecycle values."""
    customer_repository.get_by_id.return_value = customer

    created_conversation = Conversation(
        id=uuid.uuid4(),
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        channel=ConversationChannel.WHATSAPP,
        status=ConversationStatus.PENDING,
        handling_mode=ConversationHandlingMode.HUMAN,
        unread_count=0,
    )

    repository.add.return_value = created_conversation

    result = await service.create(
        customer.id,
        channel=ConversationChannel.WHATSAPP,
        status=ConversationStatus.PENDING,
        handling_mode=ConversationHandlingMode.HUMAN,
    )

    assert result.status == ConversationStatus.PENDING
    assert result.handling_mode == ConversationHandlingMode.HUMAN


@pytest.mark.asyncio
async def test_get_delegates_to_tenant_scoped_repository(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
    conversation: Conversation,
) -> None:
    """get() must delegate retrieval to the tenant-scoped repository."""
    repository.get_by_id.return_value = conversation

    result = await service.get(
        conversation_id,
    )

    assert result is conversation

    repository.get_by_id.assert_awaited_once_with(
        conversation_id,
    )


@pytest.mark.asyncio
async def test_get_returns_none_when_conversation_is_missing(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
) -> None:
    """Missing tenant-owned conversations should return None."""
    repository.get_by_id.return_value = None

    result = await service.get(
        conversation_id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_by_customer_validates_customer_first(
    service: ConversationService,
    customer_repository: AsyncMock,
    repository: AsyncMock,
    customer: Customer,
) -> None:
    """
    list_by_customer must verify that the customer exists inside the
    authorized tenant before querying conversations.
    """
    customer_repository.get_by_id.return_value = customer
    repository.get_by_customer.return_value = []

    result = await service.list_by_customer(
        customer.id,
    )

    assert result == []

    customer_repository.get_by_id.assert_awaited_once_with(
        customer.id,
    )
    repository.get_by_customer.assert_awaited_once_with(
        customer.id,
    )


@pytest.mark.asyncio
async def test_list_by_customer_returns_empty_when_customer_missing(
    service: ConversationService,
    customer_repository: AsyncMock,
    repository: AsyncMock,
    customer_id: uuid.UUID,
) -> None:
    """
    A customer invisible to the tenant should not be used to enumerate
    conversations.
    """
    customer_repository.get_by_id.return_value = None

    result = await service.list_by_customer(
        customer_id,
    )

    assert result == []
    repository.get_by_customer.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_by_status_delegates_to_repository(
    service: ConversationService,
    repository: AsyncMock,
) -> None:
    """Status filtering belongs to the repository."""
    repository.list_by_status.return_value = []

    result = await service.list_by_status(
        ConversationStatus.OPEN,
    )

    assert result == []

    repository.list_by_status.assert_awaited_once_with(
        ConversationStatus.OPEN,
    )


@pytest.mark.asyncio
async def test_list_by_channel_delegates_to_repository(
    service: ConversationService,
    repository: AsyncMock,
) -> None:
    """Channel filtering belongs to the repository."""
    repository.list_by_channel.return_value = []

    result = await service.list_by_channel(
        ConversationChannel.WHATSAPP,
    )

    assert result == []

    repository.list_by_channel.assert_awaited_once_with(
        ConversationChannel.WHATSAPP,
    )


@pytest.mark.asyncio
async def test_list_by_handling_mode_delegates_to_repository(
    service: ConversationService,
    repository: AsyncMock,
) -> None:
    """Handling-mode filtering belongs to the repository."""
    repository.list_by_handling_mode.return_value = []

    result = await service.list_by_handling_mode(
        ConversationHandlingMode.AI,
    )

    assert result == []

    repository.list_by_handling_mode.assert_awaited_once_with(
        ConversationHandlingMode.AI,
    )


@pytest.mark.asyncio
async def test_list_by_assigned_user_delegates_to_repository(
    service: ConversationService,
    repository: AsyncMock,
    assigned_user_id: uuid.UUID,
) -> None:
    """Assigned-user filtering must remain tenant-scoped."""
    repository.list_by_assigned_user.return_value = []

    result = await service.list_by_assigned_user(
        assigned_user_id,
    )

    assert result == []

    repository.list_by_assigned_user.assert_awaited_once_with(
        assigned_user_id,
    )


@pytest.mark.asyncio
async def test_change_status_updates_conversation(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
) -> None:
    """Changing status must flush and refresh the conversation."""
    repository.get_by_id.return_value = conversation

    result = await service.change_status(
        conversation.id,
        ConversationStatus.RESOLVED,
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.RESOLVED

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_change_status_returns_none_for_missing_conversation(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
) -> None:
    """Status changes must not mutate a missing conversation."""
    repository.get_by_id.return_value = None

    result = await service.change_status(
        conversation_id,
        ConversationStatus.RESOLVED,
    )

    assert result is None
    repository.db.flush.assert_not_awaited()
    repository.db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_handling_mode_updates_conversation(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
) -> None:
    """Handling-mode changes must persist through flush/refresh."""
    repository.get_by_id.return_value = conversation

    result = await service.change_handling_mode(
        conversation.id,
        ConversationHandlingMode.HUMAN,
    )

    assert result is conversation
    assert conversation.handling_mode == ConversationHandlingMode.HUMAN

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_assign_sets_assigned_user(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
    assigned_user_id: uuid.UUID,
) -> None:
    """Assignment must update the conversation assignment."""
    repository.get_by_id.return_value = conversation

    result = await service.assign(
        conversation.id,
        assigned_user_id,
    )

    assert result is conversation
    assert conversation.assigned_user_id == assigned_user_id

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_unassign_clears_assigned_user(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
    assigned_user_id: uuid.UUID,
) -> None:
    """Unassignment must clear the assigned user."""
    conversation.assigned_user_id = assigned_user_id
    repository.get_by_id.return_value = conversation

    result = await service.unassign(
        conversation.id,
    )

    assert result is conversation
    assert conversation.assigned_user_id is None

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_increment_unread_rejects_zero(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
) -> None:
    """Zero is not a valid unread increment."""
    with pytest.raises(
        ValueError,
        match="Unread increment amount must be greater than zero",
    ):
        await service.increment_unread(
            conversation_id,
            amount=0,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_increment_unread_rejects_negative_amount(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
) -> None:
    """Negative increments must be rejected."""
    with pytest.raises(
        ValueError,
        match="Unread increment amount must be greater than zero",
    ):
        await service.increment_unread(
            conversation_id,
            amount=-1,
        )

    repository.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_increment_unread_updates_counter(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
) -> None:
    """Unread count should increase by the requested amount."""
    conversation.unread_count = 2
    repository.get_by_id.return_value = conversation

    result = await service.increment_unread(
        conversation.id,
        amount=3,
    )

    assert result is conversation
    assert conversation.unread_count == 5

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_clear_unread_resets_counter(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
) -> None:
    """Clearing unread state should reset the counter to zero."""
    conversation.unread_count = 7
    repository.get_by_id.return_value = conversation

    result = await service.clear_unread(
        conversation.id,
    )

    assert result is conversation
    assert conversation.unread_count == 0

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_update_last_message_at(
    service: ConversationService,
    repository: AsyncMock,
    conversation: Conversation,
) -> None:
    """The service must persist the supplied message timestamp."""
    timestamp = datetime(
        2026,
        10,
        2,
        20,
        30,
        tzinfo=timezone.utc,
    )

    repository.get_by_id.return_value = conversation

    result = await service.update_last_message_at(
        conversation.id,
        timestamp,
    )

    assert result is conversation
    assert conversation.last_message_at == timestamp

    repository.db.flush.assert_awaited_once_with()
    repository.db.refresh.assert_awaited_once_with(
        conversation,
    )


@pytest.mark.asyncio
async def test_mutations_return_none_for_missing_conversation(
    service: ConversationService,
    repository: AsyncMock,
    conversation_id: uuid.UUID,
    assigned_user_id: uuid.UUID,
) -> None:
    """
    All conversation mutations should safely return None when the
    conversation is not visible inside the authorized tenant.
    """
    repository.get_by_id.return_value = None

    status_result = await service.change_status(
        conversation_id,
        ConversationStatus.CLOSED,
    )

    handling_result = await service.change_handling_mode(
        conversation_id,
        ConversationHandlingMode.HUMAN,
    )

    assign_result = await service.assign(
        conversation_id,
        assigned_user_id,
    )

    unassign_result = await service.unassign(
        conversation_id,
    )

    increment_result = await service.increment_unread(
        conversation_id,
    )

    clear_result = await service.clear_unread(
        conversation_id,
    )

    timestamp_result = await service.update_last_message_at(
        conversation_id,
        datetime.now(timezone.utc),
    )

    assert status_result is None
    assert handling_result is None
    assert assign_result is None
    assert unassign_result is None
    assert increment_result is None
    assert clear_result is None
    assert timestamp_result is None

    repository.db.flush.assert_not_awaited()
    repository.db.refresh.assert_not_awaited()