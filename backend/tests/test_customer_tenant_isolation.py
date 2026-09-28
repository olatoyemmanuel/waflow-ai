"""
WAFlow AI customer tenant-isolation integration tests.

These tests verify that customer data remains isolated at the API
boundary even when the same authenticated user belongs to multiple
tenants.

The tests use the real PostgreSQL database configured for the backend.

Security guarantees covered here:

- Tenant A lists only Tenant A customers.
- Tenant A cannot retrieve a Tenant B customer by ID.
- Tenant A cannot update a Tenant B customer by ID.
- Tenant A cannot archive a Tenant B customer by ID.
- Tenant A cannot restore a Tenant B customer by ID.
- Tenant A search results exclude Tenant B customers.
- Tenant A status-filter totals exclude Tenant B customers.
- Tenant A pagination totals exclude Tenant B customers.
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.main import app
from app.modules.auth.security import create_access_token, hash_password
from app.modules.customers.models import Customer, CustomerStatus
from app.modules.identity.models import (
    Membership,
    MembershipStatus,
    Role,
    Tenant,
    User,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a real asynchronous PostgreSQL session.
    """

    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provide an HTTPX client for the real WAFlow AI FastAPI application.

    The database dependency is overridden so API requests use the same
    PostgreSQL test database as the existing integration tests.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """
        Use a real PostgreSQL session for API dependency resolution.
        """

        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(
        app=app,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


async def get_role(
    db_session: AsyncSession,
    role_name: str,
) -> Role:
    """
    Resolve an existing seeded RBAC role.
    """

    result = await db_session.execute(
        select(Role).where(
            Role.name == role_name,
        ),
    )

    role = result.scalar_one_or_none()

    assert role is not None, (
        f"Required seeded role {role_name!r} does not exist."
    )

    return role


async def create_multi_tenant_identity(
    db_session: AsyncSession,
) -> tuple[User, Tenant, Tenant]:
    """
    Create one user with active OWNER memberships in two tenants.

    This is important for tenant-isolation testing because the
    authenticated user is legitimately allowed to access both tenants.
    The tests therefore prove that tenant data boundaries are enforced
    independently of authentication and RBAC.
    """

    unique_id = uuid4().hex

    user = User(
        email=f"test-tenant-isolation-{unique_id}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        first_name="Tenant",
        last_name="Isolation",
        phone="+2348000000000",
        is_email_verified=True,
    )

    tenant_a = Tenant(
        name=f"Isolation Tenant A {unique_id}",
        slug=f"isolation-a-{unique_id}",
    )

    tenant_b = Tenant(
        name=f"Isolation Tenant B {unique_id}",
        slug=f"isolation-b-{unique_id}",
    )

    role = await get_role(
        db_session,
        "OWNER",
    )

    membership_a = Membership(
        user=user,
        tenant=tenant_a,
        role=role,
        status=MembershipStatus.ACTIVE,
    )

    membership_b = Membership(
        user=user,
        tenant=tenant_b,
        role=role,
        status=MembershipStatus.ACTIVE,
    )

    db_session.add(user)
    db_session.add(tenant_a)
    db_session.add(tenant_b)
    db_session.add(membership_a)
    db_session.add(membership_b)

    await db_session.commit()

    await db_session.refresh(user)
    await db_session.refresh(tenant_a)
    await db_session.refresh(tenant_b)

    return user, tenant_a, tenant_b


async def create_test_customer(
    db_session: AsyncSession,
    tenant_id: UUID,
    *,
    first_name: str,
    last_name: str = "Customer",
    status: CustomerStatus = CustomerStatus.ACTIVE,
    company_name: str = "Isolation Test Company",
) -> Customer:
    """
    Create a customer directly inside the supplied tenant.
    """

    unique_id = uuid4().hex

    customer = Customer(
        tenant_id=tenant_id,
        first_name=first_name,
        last_name=last_name,
        phone=f"+23480{unique_id[:8]}",
        email=f"{unique_id}@example.com",
        company_name=company_name,
        status=status,
    )

    db_session.add(customer)

    await db_session.commit()
    await db_session.refresh(customer)

    return customer


async def cleanup_multi_tenant_identity(
    db_session: AsyncSession,
    user_id: UUID,
    tenant_a_id: UUID,
    tenant_b_id: UUID,
) -> None:
    """
    Remove both tenants and the test user.

    Customer rows are removed through the tenant foreign-key cascade.
    Membership rows are removed through their configured relationships.
    """

    user = await db_session.get(
        User,
        user_id,
    )

    if user is not None:
        await db_session.delete(user)

    await db_session.flush()

    tenant_a = await db_session.get(
        Tenant,
        tenant_a_id,
    )

    if tenant_a is not None:
        await db_session.delete(tenant_a)

    tenant_b = await db_session.get(
        Tenant,
        tenant_b_id,
    )

    if tenant_b is not None:
        await db_session.delete(tenant_b)

    await db_session.commit()


def authorization_headers(
    user_id: UUID,
) -> dict[str, str]:
    """
    Create a valid bearer Authorization header.
    """

    token = create_access_token(
        user_id,
    )

    return {
        "Authorization": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# Tenant-scoped collection isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_only_customers_from_selected_tenant(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Listing Tenant A must never include customers from Tenant B.

    The authenticated user has OWNER membership in both tenants, so this
    test specifically validates data isolation rather than membership
    authorization.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_a_1 = await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="TenantA-One",
    )

    customer_a_2 = await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="TenantA-Two",
    )

    customer_b_1 = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB-One",
    )

    customer_b_2 = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB-Two",
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant_a.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    returned_ids = {
        item["id"]
        for item in body["data"]["items"]
    }

    assert returned_ids == {
        str(customer_a_1.id),
        str(customer_a_2.id),
    }

    assert str(customer_b_1.id) not in returned_ids
    assert str(customer_b_2.id) not in returned_ids
    assert body["data"]["total"] == 2

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


# ---------------------------------------------------------------------------
# Resource ID isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cannot_cross_tenant_boundary(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A Tenant B customer ID must behave as nonexistent when the request
    is scoped to Tenant A.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_b = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB",
    )

    response = await client.get(
        f"/api/v1/customers/{customer_b.id}?tenant_id={tenant_a.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


@pytest.mark.asyncio
async def test_update_cannot_cross_tenant_boundary(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A Tenant B customer cannot be modified through a Tenant A context.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_b = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB",
    )

    response = await client.patch(
        f"/api/v1/customers/{customer_b.id}?tenant_id={tenant_a.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "ShouldNotChange",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."

    await db_session.refresh(customer_b)

    assert customer_b.first_name == "TenantB"
    assert customer_b.tenant_id == tenant_b.id

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


@pytest.mark.asyncio
async def test_archive_cannot_cross_tenant_boundary(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A Tenant B customer cannot be archived through a Tenant A context.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_b = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB",
    )

    response = await client.post(
        f"/api/v1/customers/{customer_b.id}/archive"
        f"?tenant_id={tenant_a.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."

    await db_session.refresh(customer_b)

    assert customer_b.status == CustomerStatus.ACTIVE

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


@pytest.mark.asyncio
async def test_restore_cannot_cross_tenant_boundary(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A Tenant B customer cannot be restored through a Tenant A context.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_b = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="TenantB",
        status=CustomerStatus.ARCHIVED,
    )

    response = await client.post(
        f"/api/v1/customers/{customer_b.id}/restore"
        f"?tenant_id={tenant_a.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."

    await db_session.refresh(customer_b)

    assert customer_b.status == CustomerStatus.ARCHIVED

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


# ---------------------------------------------------------------------------
# Search isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_results_are_tenant_scoped(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Search results and search totals must exclude matching customers from
    another tenant.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    customer_a_1 = await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="Shared-A-One",
    )

    customer_a_2 = await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="Shared-A-Two",
    )

    customer_b_1 = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="Shared-B-One",
    )

    customer_b_2 = await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="Shared-B-Two",
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant_a.id}"
        "&search=Shared",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    returned_ids = {
        item["id"]
        for item in body["data"]["items"]
    }

    assert returned_ids == {
        str(customer_a_1.id),
        str(customer_a_2.id),
    }

    assert str(customer_b_1.id) not in returned_ids
    assert str(customer_b_2.id) not in returned_ids

    assert body["data"]["total"] == 2
    assert body["data"]["pages"] == 1

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


# ---------------------------------------------------------------------------
# Status-filter isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_filter_total_is_tenant_scoped(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Status-filtered totals must count only customers in the selected
    tenant.
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="Active-A-One",
        status=CustomerStatus.ACTIVE,
    )

    await create_test_customer(
        db_session,
        tenant_a.id,
        first_name="Active-A-Two",
        status=CustomerStatus.ACTIVE,
    )

    await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="Active-B-One",
        status=CustomerStatus.ACTIVE,
    )

    await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="Active-B-Two",
        status=CustomerStatus.ACTIVE,
    )

    await create_test_customer(
        db_session,
        tenant_b.id,
        first_name="Active-B-Three",
        status=CustomerStatus.ACTIVE,
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant_a.id}"
        "&status=active",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["total"] == 2
    assert body["data"]["pages"] == 1
    assert len(body["data"]["items"]) == 2

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )


# ---------------------------------------------------------------------------
# Pagination isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_total_is_tenant_scoped(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Pagination totals must count only records in the selected tenant.

    Tenant A receives three customers while Tenant B receives seven.
    A page-size of two therefore produces:

        Tenant A → total 3, pages 2
        Tenant B → total 7, pages 4
    """

    user, tenant_a, tenant_b = await create_multi_tenant_identity(
        db_session,
    )

    for index in range(3):
        await create_test_customer(
            db_session,
            tenant_a.id,
            first_name=f"Pagination-A-{index}",
        )

    for index in range(7):
        await create_test_customer(
            db_session,
            tenant_b.id,
            first_name=f"Pagination-B-{index}",
        )

    response_a = await client.get(
        f"/api/v1/customers?tenant_id={tenant_a.id}"
        "&page=1&page_size=2",
        headers=authorization_headers(user.id),
    )

    assert response_a.status_code == 200

    body_a = response_a.json()

    assert body_a["data"]["total"] == 3
    assert body_a["data"]["pages"] == 2
    assert len(body_a["data"]["items"]) == 2

    response_b = await client.get(
        f"/api/v1/customers?tenant_id={tenant_b.id}"
        "&page=1&page_size=2",
        headers=authorization_headers(user.id),
    )

    assert response_b.status_code == 200

    body_b = response_b.json()

    assert body_b["data"]["total"] == 7
    assert body_b["data"]["pages"] == 4
    assert len(body_b["data"]["items"]) == 2

    await cleanup_multi_tenant_identity(
        db_session,
        user.id,
        tenant_a.id,
        tenant_b.id,
    )