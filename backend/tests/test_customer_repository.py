"""
Tests for the tenant-scoped CustomerRepository.

These tests verify customer-specific repository operations and ensure
that they execute through the repository's tenant-scoped query boundary.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.pagination import PaginationParams
from app.modules.customers.models import CustomerStatus
from app.modules.customers.repository import CustomerRepository


@pytest.fixture
def tenant_id():
    """Return a tenant ID used by the repository under test."""
    return uuid4()


@pytest.fixture
def db():
    """Return an async database-session mock."""
    return AsyncMock()


@pytest.fixture
def repository(db, tenant_id):
    """Return a customer repository bound to one tenant."""
    return CustomerRepository(
        db=db,
        tenant_id=tenant_id,
    )


def _mock_result(records):
    """
    Build a SQLAlchemy-like synchronous Result mock.

    AsyncSession.execute() is asynchronous and therefore mocked with
    AsyncMock. The Result object returned after awaiting execute(),
    however, exposes synchronous methods such as scalar_one_or_none(),
    scalars(), and ScalarResult.all().
    """
    result = MagicMock()

    if len(records) == 1:
        result.scalar_one_or_none.return_value = records[0]
    else:
        result.scalar_one_or_none.return_value = None

    scalar_result = MagicMock()
    scalar_result.all.return_value = records

    result.scalars.return_value = scalar_result

    return result


@pytest.mark.asyncio
async def test_get_by_email_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Verify email lookup executes through the tenant-scoped repository.
    """
    customer = object()

    db.execute.return_value = _mock_result(
        [customer],
    )

    result = await repository.get_by_email(
        "customer@example.com",
    )

    assert result is customer
    assert repository.tenant_id == tenant_id

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_phone_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Verify phone lookup executes through the tenant-scoped repository.
    """
    customer = object()

    db.execute.return_value = _mock_result(
        [customer],
    )

    result = await repository.get_by_phone(
        "+2348012345678",
    )

    assert result is customer
    assert repository.tenant_id == tenant_id

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_by_status_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Verify status filtering is combined with tenant filtering.
    """
    customer = object()

    db.execute.return_value = _mock_result(
        [customer],
    )

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    result = await repository.list_by_status(
        status=CustomerStatus.ACTIVE,
        pagination=pagination,
    )

    assert result == [customer]
    assert repository.tenant_id == tenant_id

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Verify customer search executes through the tenant-scoped SELECT.
    """
    customer = object()

    db.execute.return_value = _mock_result(
        [customer],
    )

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    result = await repository.search(
        query="Acme",
        pagination=pagination,
    )

    assert result == [customer]
    assert repository.tenant_id == tenant_id

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_with_blank_query_delegates_to_tenant_scoped_list(
    repository,
    db,
):
    """
    A blank search should behave like a normal tenant-scoped list.
    """
    customer = object()

    repository.list = AsyncMock(
        return_value=[customer],
    )

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    result = await repository.search(
        query="   ",
        pagination=pagination,
    )

    assert result == [customer]

    repository.list.assert_awaited_once_with(
        pagination,
    )

    db.execute.assert_not_awaited()