"""
Tests for the tenant-scoped ConversationRepository.

These tests focus on repository construction and SQL query composition.
Full database integration and tenant-isolation behavior will be expanded
during the dedicated 4F.11 tenant-isolation milestone.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.conversations.models import (
    Conversation,
    ConversationChannel,
    ConversationHandlingMode,
    ConversationStatus,
)
from app.modules.conversations.repository import ConversationRepository


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Provide a deterministic tenant UUID for repository tests."""
    return uuid.uuid4()


@pytest.fixture
def session() -> AsyncMock:
    """Provide a mocked asynchronous SQLAlchemy session."""
    return AsyncMock()


@pytest.fixture
def repository(
    session: AsyncMock,
    tenant_id: uuid.UUID,
) -> ConversationRepository:
    """Create a repository bound to the test tenant."""
    return ConversationRepository(
        session=session,
        tenant_id=tenant_id,
    )


def test_repository_uses_conversation_model(
    repository: ConversationRepository,
) -> None:
    """The repository must be specialized for Conversation."""
    assert repository.model is Conversation


def test_repository_uses_supplied_tenant(
    repository: ConversationRepository,
    tenant_id: uuid.UUID,
) -> None:
    """The repository must retain the tenant supplied by TenantContext."""
    assert repository.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_get_by_customer_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """get_by_customer must include tenant ownership in its query."""
    customer_id = uuid.uuid4()

    scalars = MagicMock()
    scalars.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalars

    session.execute.return_value = result

    conversations = await repository.get_by_customer(customer_id)

    assert conversations == []
    session.execute.assert_awaited_once()

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.customer_id" in sql


@pytest.mark.asyncio
async def test_count_by_customer_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """count_by_customer must include tenant ownership in its query."""
    customer_id = uuid.uuid4()

    result = MagicMock()
    result.scalar_one.return_value = 3

    session.execute.return_value = result

    count = await repository.count_by_customer(customer_id)

    assert count == 3

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.customer_id" in sql


@pytest.mark.asyncio
async def test_list_by_status_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """list_by_status must restrict results to the repository tenant."""
    scalars = MagicMock()
    scalars.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalars

    session.execute.return_value = result

    conversations = await repository.list_by_status(
        ConversationStatus.OPEN,
    )

    assert conversations == []

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.status" in sql


@pytest.mark.asyncio
async def test_count_by_status_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """count_by_status must restrict the count to the repository tenant."""
    result = MagicMock()
    result.scalar_one.return_value = 5

    session.execute.return_value = result

    count = await repository.count_by_status(
        ConversationStatus.OPEN,
    )

    assert count == 5

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.status" in sql


@pytest.mark.asyncio
async def test_list_by_channel_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """list_by_channel must restrict results to the repository tenant."""
    scalars = MagicMock()
    scalars.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalars

    session.execute.return_value = result

    conversations = await repository.list_by_channel(
        ConversationChannel.WHATSAPP,
    )

    assert conversations == []

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.channel" in sql


@pytest.mark.asyncio
async def test_count_by_channel_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """count_by_channel must restrict the count to the repository tenant."""
    result = MagicMock()
    result.scalar_one.return_value = 4

    session.execute.return_value = result

    count = await repository.count_by_channel(
        ConversationChannel.WHATSAPP,
    )

    assert count == 4

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.channel" in sql


@pytest.mark.asyncio
async def test_list_by_handling_mode_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """list_by_handling_mode must restrict results to the tenant."""
    scalars = MagicMock()
    scalars.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalars

    session.execute.return_value = result

    conversations = await repository.list_by_handling_mode(
        ConversationHandlingMode.AI,
    )

    assert conversations == []

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.handling_mode" in sql


@pytest.mark.asyncio
async def test_count_by_handling_mode_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """count_by_handling_mode must restrict the count to the tenant."""
    result = MagicMock()
    result.scalar_one.return_value = 6

    session.execute.return_value = result

    count = await repository.count_by_handling_mode(
        ConversationHandlingMode.HUMAN,
    )

    assert count == 6

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.handling_mode" in sql


@pytest.mark.asyncio
async def test_list_by_assigned_user_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """list_by_assigned_user must restrict results to the tenant."""
    assigned_user_id = uuid.uuid4()

    scalars = MagicMock()
    scalars.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalars

    session.execute.return_value = result

    conversations = await repository.list_by_assigned_user(
        assigned_user_id,
    )

    assert conversations == []

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.assigned_user_id" in sql


@pytest.mark.asyncio
async def test_count_by_assigned_user_is_tenant_scoped(
    repository: ConversationRepository,
    session: AsyncMock,
) -> None:
    """count_by_assigned_user must restrict the count to the tenant."""
    assigned_user_id = uuid.uuid4()

    result = MagicMock()
    result.scalar_one.return_value = 2

    session.execute.return_value = result

    count = await repository.count_by_assigned_user(
        assigned_user_id,
    )

    assert count == 2

    statement = session.execute.await_args.args[0]
    sql = str(statement)

    assert "conversations.tenant_id" in sql
    assert "conversations.assigned_user_id" in sql