"""
Tests for the tenant-scoped CustomerRepository.

These tests verify:

- email lookup is tenant-scoped
- phone lookup is tenant-scoped
- status listing is tenant-scoped
- status counting is tenant-scoped
- customer search is tenant-scoped
- search counting is tenant-scoped
- blank search delegates to the normal tenant-scoped operations
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.pagination import PaginationParams
from app.modules.customers.models import CustomerStatus
from app.modules.customers.repository import CustomerRepository


@pytest.fixture
def db():
    """
    Return a mocked asynchronous SQLAlchemy session.
    """

    return AsyncMock()


@pytest.fixture
def tenant_id():
    """
    Return the tenant used by the repository under test.
    """

    return uuid4()


@pytest.fixture
def repository(db, tenant_id):
    """
    Build a CustomerRepository bound to one tenant.
    """

    return CustomerRepository(
        db=db,
        tenant_id=tenant_id,
    )


def assert_statement_contains_tenant(
    statement,
    tenant_id,
):
    """
    Verify that the generated SQL contains the repository tenant
    parameter.

    SQLAlchemy represents literal values as bound parameters, so the test
    inspects compiled parameter values instead of searching for the UUID
    string inside the SQL text.
    """

    compiled = statement.compile()

    assert tenant_id in compiled.params.values()


@pytest.mark.asyncio
async def test_get_by_email_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Email lookup must include the repository tenant boundary.
    """

    customer = object()

    result = MagicMock()
    result.scalar_one_or_none.return_value = customer

    db.execute = AsyncMock(
        return_value=result,
    )

    response = await repository.get_by_email(
        "john@example.com",
    )

    assert response is customer

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_get_by_phone_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Phone lookup must include the repository tenant boundary.
    """

    customer = object()

    result = MagicMock()
    result.scalar_one_or_none.return_value = customer

    db.execute = AsyncMock(
        return_value=result,
    )

    response = await repository.get_by_phone(
        "+2348012345678",
    )

    assert response is customer

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_list_by_status_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Status-filtered listing must include the repository tenant boundary.
    """

    customers = [
        object(),
        object(),
    ]

    result = MagicMock()
    result.scalars.return_value.all.return_value = customers

    db.execute = AsyncMock(
        return_value=result,
    )

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    response = await repository.list_by_status(
        status=CustomerStatus.ACTIVE,
        pagination=pagination,
    )

    assert response == customers

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_count_by_status_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Status counts must include the repository tenant boundary.
    """

    result = MagicMock()
    result.scalar_one.return_value = 3

    db.execute = AsyncMock(
        return_value=result,
    )

    count = await repository.count_by_status(
        CustomerStatus.ACTIVE,
    )

    assert count == 3

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_search_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Customer search must include the repository tenant boundary.
    """

    customers = [
        object(),
        object(),
    ]

    result = MagicMock()
    result.scalars.return_value.all.return_value = customers

    db.execute = AsyncMock(
        return_value=result,
    )

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    response = await repository.search(
        query="john",
        pagination=pagination,
    )

    assert response == customers

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_count_search_is_tenant_scoped(
    repository,
    db,
    tenant_id,
):
    """
    Search counts must include the repository tenant boundary.
    """

    result = MagicMock()
    result.scalar_one.return_value = 5

    db.execute = AsyncMock(
        return_value=result,
    )

    count = await repository.count_search(
        "john",
    )

    assert count == 5

    statement = db.execute.await_args.args[0]

    assert_statement_contains_tenant(
        statement,
        tenant_id,
    )


@pytest.mark.asyncio
async def test_blank_search_delegates_to_tenant_scoped_list(
    repository,
):
    """
    A blank search query should behave like the normal paginated list.
    """

    customers = [
        object(),
    ]

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    repository.list = AsyncMock(
        return_value=customers,
    )

    response = await repository.search(
        query="   ",
        pagination=pagination,
    )

    assert response == customers

    repository.list.assert_awaited_once_with(
        pagination,
    )


@pytest.mark.asyncio
async def test_blank_search_count_delegates_to_tenant_scoped_count(
    repository,
):
    """
    A blank search count should behave like the normal tenant count.
    """

    repository.count = AsyncMock(
        return_value=7,
    )

    count = await repository.count_search(
        "   ",
    )

    assert count == 7

    repository.count.assert_awaited_once()