"""
Tests for the CustomerService application layer.

These tests verify:

- tenant identity comes from TenantContext
- repository/service tenant mismatch is rejected
- customer creation is tenant-owned
- duplicate email and phone values are rejected
- tenant-scoped retrieval is delegated to the repository
- updates preserve customer ownership
- archive and restore use lifecycle status
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.pagination import PaginationParams
from app.modules.auth.dependencies import TenantContext
from app.modules.customers.models import Customer, CustomerStatus
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate
from app.modules.customers.service import CustomerService


def build_tenant_context(
    tenant_id=None,
) -> TenantContext:
    """
    Build a valid TenantContext for service tests.
    """
    return TenantContext(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        membership_id=uuid4(),
        role_id=uuid4(),
        role_name="OWNER",
    )


def build_customer(
    tenant_id,
) -> Customer:
    """
    Build a customer belonging to the supplied tenant.
    """
    return Customer(
        tenant_id=tenant_id,
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+2348012345678",
        company_name="Example Ltd",
    )


@pytest.fixture
def tenant_context():
    """Return a tenant context for the tests."""
    return build_tenant_context()


@pytest.fixture
def repository(tenant_context):
    """
    Return a mocked CustomerRepository bound to the test tenant.

    The service constructor checks repository.tenant_id, so the mock must
    expose the same tenant boundary as TenantContext.
    """
    repository = AsyncMock()
    repository.tenant_id = tenant_context.tenant_id

    return repository


@pytest.fixture
def service(repository, tenant_context):
    """Return a CustomerService under test."""
    return CustomerService(
        repository=repository,
        tenant_context=tenant_context,
    )


@pytest.mark.asyncio
async def test_service_rejects_repository_tenant_mismatch():
    """
    A repository from another tenant must never be accepted.
    """
    tenant_context = build_tenant_context()

    repository = AsyncMock()
    repository.tenant_id = uuid4()

    with pytest.raises(
        ValueError,
        match="Repository tenant does not match",
    ):
        CustomerService(
            repository=repository,
            tenant_context=tenant_context,
        )


@pytest.mark.asyncio
async def test_create_derives_tenant_from_context(
    service,
    repository,
    tenant_context,
):
    """
    Customer creation must use TenantContext as the ownership source.
    """
    repository.get_by_email.return_value = None
    repository.get_by_phone.return_value = None

    data = CustomerCreate(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+2348012345678",
    )

    created_customer = build_customer(
        tenant_context.tenant_id,
    )

    repository.add.return_value = created_customer

    result = await service.create(data)

    assert result is created_customer

    created_entity = repository.add.await_args.args[0]

    assert created_entity.tenant_id == tenant_context.tenant_id
    assert created_entity.first_name == "John"
    assert created_entity.last_name == "Doe"
    assert created_entity.email == "john@example.com"
    assert created_entity.phone == "+2348012345678"

    repository.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_email(
    service,
    repository,
):
    """
    A duplicate email inside the same tenant must be rejected.
    """
    existing_customer = object()

    repository.get_by_email.return_value = existing_customer

    data = CustomerCreate(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
    )

    with pytest.raises(
        ValueError,
        match="email already exists",
    ):
        await service.create(data)

    repository.add.assert_not_awaited()
    repository.get_by_phone.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_phone(
    service,
    repository,
):
    """
    A duplicate phone number inside the same tenant must be rejected.
    """
    repository.get_by_email.return_value = None
    repository.get_by_phone.return_value = object()

    data = CustomerCreate(
        first_name="John",
        last_name="Doe",
        phone="+2348012345678",
    )

    with pytest.raises(
        ValueError,
        match="phone number already exists",
    ):
        await service.create(data)

    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_delegates_to_tenant_scoped_repository(
    service,
    repository,
):
    """
    Customer retrieval must use the repository's tenant scope.
    """
    customer_id = uuid4()
    customer = object()

    repository.get_by_id.return_value = customer

    result = await service.get(customer_id)

    assert result is customer

    repository.get_by_id.assert_awaited_once_with(
        customer_id,
    )


@pytest.mark.asyncio
async def test_list_delegates_to_base_tenant_service(
    service,
    repository,
):
    """
    Normal customer listing uses the reusable tenant-scoped service.
    """
    customers = [object(), object()]

    repository.list.return_value = customers
    repository.count.return_value = 2

    pagination = PaginationParams(
        page=1,
        page_size=20,
    )

    records, metadata = await service.list(
        pagination,
    )

    assert records == customers
    assert metadata.total == 2

    repository.list.assert_awaited_once_with(
        pagination,
    )

    repository.count.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_returns_none_for_missing_customer(
    service,
    repository,
):
    """
    A customer outside the tenant behaves as nonexistent.
    """
    repository.get_by_id.return_value = None

    customer_id = uuid4()

    data = CustomerUpdate(
        first_name="Updated",
    )

    result = await service.update(
        customer_id,
        data,
    )

    assert result is None

    repository.get_by_id.assert_awaited_once_with(
        customer_id,
    )


@pytest.mark.asyncio
async def test_update_changes_allowed_fields(
    service,
    repository,
    tenant_context,
):
    """
    Customer updates should modify only fields represented by the
    CustomerUpdate schema.
    """
    customer = build_customer(
        tenant_context.tenant_id,
    )

    repository.get_by_id.return_value = customer

    data = CustomerUpdate(
        first_name="Jane",
        company_name="New Company",
    )

    result = await service.update(
        customer.id,
        data,
    )

    assert result is customer
    assert customer.first_name == "Jane"
    assert customer.company_name == "New Company"

    assert customer.tenant_id == tenant_context.tenant_id

    repository.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rejects_duplicate_email(
    service,
    repository,
    tenant_context,
):
    """
    Updating to another customer's email must be rejected.
    """
    customer = build_customer(
        tenant_context.tenant_id,
    )

    other_customer = build_customer(
        tenant_context.tenant_id,
    )

    other_customer.id = uuid4()

    repository.get_by_id.return_value = customer
    repository.get_by_email.return_value = other_customer

    data = CustomerUpdate(
        email="other@example.com",
    )

    with pytest.raises(
        ValueError,
        match="email already exists",
    ):
        await service.update(
            customer.id,
            data,
        )

    repository.db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_allows_same_customer_email(
    service,
    repository,
    tenant_context,
):
    """
    A customer may retain its own existing email address.
    """
    customer = build_customer(
        tenant_context.tenant_id,
    )

    repository.get_by_id.return_value = customer
    repository.get_by_email.return_value = customer

    data = CustomerUpdate(
        email=customer.email,
    )

    result = await service.update(
        customer.id,
        data,
    )

    assert result is customer
    repository.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_changes_status(
    service,
    repository,
    tenant_context,
):
    """
    Normal customer removal is represented as ARCHIVED rather than a
    physical database deletion.
    """
    customer = build_customer(
        tenant_context.tenant_id,
    )

    repository.get_by_id.return_value = customer

    result = await service.archive(
        customer.id,
    )

    assert result is customer
    assert customer.status == CustomerStatus.ARCHIVED

    repository.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_changes_status(
    service,
    repository,
    tenant_context,
):
    """
    An archived customer can be restored to ACTIVE status.
    """
    customer = build_customer(
        tenant_context.tenant_id,
    )

    customer.status = CustomerStatus.ARCHIVED

    repository.get_by_id.return_value = customer

    result = await service.restore(
        customer.id,
    )

    assert result is customer
    assert customer.status == CustomerStatus.ACTIVE

    repository.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_returns_none_for_missing_customer(
    service,
    repository,
):
    """
    Archive must not affect a nonexistent tenant-scoped customer.
    """
    repository.get_by_id.return_value = None

    result = await service.archive(
        uuid4(),
    )

    assert result is None

    repository.db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_restore_returns_none_for_missing_customer(
    service,
    repository,
):
    """
    Restore must not affect a nonexistent tenant-scoped customer.
    """
    repository.get_by_id.return_value = None

    result = await service.restore(
        uuid4(),
    )

    assert result is None

    repository.db.flush.assert_not_awaited()