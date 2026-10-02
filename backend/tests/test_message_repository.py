"""
Tests for the tenant-scoped Message repository.

These tests focus on repository behavior and query construction.

Database integration and cross-tenant persistence behavior will receive
additional coverage during the later 4F.11 tenant-isolation milestone.
"""

from __future__ import annotations

import uuid

from sqlalchemy.sql import Select

from app.core.repositories import TenantScopedRepository
from app.modules.messages.models import (
    Message,
    MessageDirection,
    MessageSenderType,
    MessageStatus,
    MessageType,
)
from app.modules.messages.repository import MessageRepository


def test_message_repository_inherits_tenant_scoped_repository() -> None:
    """MessageRepository must use the shared tenant-scoped repository."""
    assert issubclass(MessageRepository, TenantScopedRepository)


def test_message_repository_uses_message_model() -> None:
    """MessageRepository must be bound to the Message model."""
    repository = MessageRepository(
        session=None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
    )

    assert repository.model is Message


def test_message_repository_stores_tenant_boundary() -> None:
    """Repository tenant ownership must be established at construction."""
    tenant_id = uuid.uuid4()

    repository = MessageRepository(
        session=None,  # type: ignore[arg-type]
        tenant_id=tenant_id,
    )

    assert repository.tenant_id == tenant_id


def test_base_query_is_select_statement() -> None:
    """The repository base query must be a SQLAlchemy Select."""
    repository = MessageRepository(
        session=None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
    )

    statement = repository._base_query()

    assert isinstance(statement, Select)


def test_base_query_targets_message_model() -> None:
    """The base query must select Message entities."""
    repository = MessageRepository(
        session=None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
    )

    statement = repository._base_query()

    assert statement.column_descriptions[0]["entity"] is Message


def test_base_query_contains_tenant_boundary() -> None:
    """The base query must contain tenant filtering."""
    tenant_id = uuid.uuid4()

    repository = MessageRepository(
        session=None,  # type: ignore[arg-type]
        tenant_id=tenant_id,
    )

    statement = repository._base_query()

    compiled = str(statement)

    assert "messages.tenant_id" in compiled


def test_repository_exposes_provider_message_lookup() -> None:
    """Provider message lookup must exist for webhook idempotency."""
    assert hasattr(
        MessageRepository,
        "get_by_provider_message_id",
    )


def test_repository_exposes_conversation_queries() -> None:
    """Conversation-specific message queries must exist."""
    assert hasattr(MessageRepository, "list_by_conversation")
    assert hasattr(MessageRepository, "count_by_conversation")


def test_repository_exposes_direction_queries() -> None:
    """Direction filtering and counting must exist."""
    assert hasattr(MessageRepository, "list_by_direction")
    assert hasattr(MessageRepository, "count_by_direction")


def test_repository_exposes_sender_type_queries() -> None:
    """Sender-type filtering and counting must exist."""
    assert hasattr(MessageRepository, "list_by_sender_type")
    assert hasattr(MessageRepository, "count_by_sender_type")


def test_repository_exposes_message_type_queries() -> None:
    """Message-type filtering and counting must exist."""
    assert hasattr(MessageRepository, "list_by_message_type")
    assert hasattr(MessageRepository, "count_by_message_type")


def test_repository_exposes_status_queries() -> None:
    """Status filtering and counting must exist."""
    assert hasattr(MessageRepository, "list_by_status")
    assert hasattr(MessageRepository, "count_by_status")


def test_message_repository_accepts_expected_enums() -> None:
    """Repository methods must use the Message domain enums."""
    assert MessageDirection.INBOUND.value == "inbound"
    assert MessageSenderType.CUSTOMER.value == "customer"
    assert MessageType.TEXT.value == "text"
    assert MessageStatus.PENDING.value == "pending"