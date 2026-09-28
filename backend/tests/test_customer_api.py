"""
WAFlow AI customer API authorization integration tests.

These tests verify that Customer API endpoints enforce the existing
database-backed RBAC permission model and tenant authorization boundary.

Coverage includes:

- missing authentication
- invalid authentication
- tenant membership isolation
- customers.read
- customers.create
- customers.update
- customers.delete
- archive authorization
- restore authorization
- prevention of archive through ordinary update
- authorized customer operations

The tests use the real PostgreSQL database configured for the backend.
Each test creates isolated users and tenants and removes them afterward.
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
    PostgreSQL test environment as the existing integration tests.
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


async def create_test_identity(
    db_session: AsyncSession,
    role_name: str,
) -> tuple[User, Tenant, Membership]:
    """
    Create a unique user, tenant, and membership.
    """

    unique_id = uuid4().hex

    user = User(
        email=f"test-customer-api-{unique_id}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        first_name="Customer",
        last_name="API",
        phone="+2348000000000",
        is_email_verified=True,
    )

    tenant = Tenant(
        name=f"Customer API Test Tenant {unique_id}",
        slug=f"customer-api-{unique_id}",
    )

    role = await get_role(
        db_session,
        role_name,
    )

    membership = Membership(
        user=user,
        tenant=tenant,
        role=role,
        status=MembershipStatus.ACTIVE,
    )

    db_session.add(user)
    db_session.add(tenant)
    db_session.add(membership)

    await db_session.commit()

    await db_session.refresh(user)
    await db_session.refresh(tenant)
    await db_session.refresh(membership)

    return user, tenant, membership


async def create_test_customer(
    db_session: AsyncSession,
    tenant_id: UUID,
    *,
    first_name: str = "John",
    last_name: str = "Doe",
    email: str | None = None,
    status: CustomerStatus = CustomerStatus.ACTIVE,
) -> Customer:
    """
    Create a customer directly in PostgreSQL for endpoint tests that
    require an existing resource.
    """

    unique_id = uuid4().hex

    customer = Customer(
        tenant_id=tenant_id,
        first_name=first_name,
        last_name=last_name,
        phone=f"+23480{unique_id[:8]}",
        email=email or f"customer-{unique_id}@example.com",
        company_name="API Test Company",
        status=status,
    )

    db_session.add(customer)

    await db_session.commit()
    await db_session.refresh(customer)

    return customer


async def cleanup_test_identity(
    db_session: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    """
    Remove the test user and tenant.

    Customer and membership rows are removed through the configured
    database foreign-key cascade relationships.
    """

    user = await db_session.get(
        User,
        user_id,
    )

    if user is not None:
        await db_session.delete(user)

    await db_session.flush()

    tenant = await db_session.get(
        Tenant,
        tenant_id,
    )

    if tenant is not None:
        await db_session.delete(tenant)

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
# Authentication and tenant boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_list_requires_authentication(
    client: httpx.AsyncClient,
) -> None:
    """
    Customer listing must reject requests without authentication.
    """

    response = await client.get(
        "/api/v1/customers?tenant_id=00000000-0000-0000-0000-000000000001",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


@pytest.mark.asyncio
async def test_customer_list_rejects_invalid_token(
    client: httpx.AsyncClient,
) -> None:
    """
    Customer listing must reject invalid bearer tokens.
    """

    response = await client.get(
        "/api/v1/customers?tenant_id=00000000-0000-0000-0000-000000000001",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid or expired access token."
    )


@pytest.mark.asyncio
async def test_customer_list_rejects_user_from_another_tenant(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    An authenticated user cannot select a tenant where they have no
    active membership.
    """

    user, user_tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    other_user, other_tenant, _ = await create_test_identity(
        db_session,
        "OWNER",
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={other_tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have access to this tenant."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        user_tenant.id,
    )

    await cleanup_test_identity(
        db_session,
        other_user.id,
        other_tenant.id,
    )


# ---------------------------------------------------------------------------
# customers.read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_can_list_customers(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    VIEWER has customers.read according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "VIEWER",
    )

    await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert len(body["data"]["items"]) == 1
    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 20
    assert body["data"]["pages"] == 1

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_viewer_can_get_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    VIEWER has customers.read and can retrieve a customer.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "VIEWER",
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.get(
        f"/api/v1/customers/{customer.id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(customer.id)
    assert body["data"]["first_name"] == "John"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# customers.create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_can_create_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    AGENT has customers.create according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone": "+2348011111111",
            "company_name": "Analytical Engines Ltd",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["first_name"] == "Ada"
    assert body["data"]["last_name"] == "Lovelace"
    assert body["data"]["email"] == "ada@example.com"
    assert body["data"]["status"] == "active"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_viewer_cannot_create_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    VIEWER does not have customers.create.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "VIEWER",
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "viewer-create@example.com",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# customers.update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_can_update_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    MANAGER has customers.update according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "MANAGER",
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.patch(
        f"/api/v1/customers/{customer.id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Updated",
            "company_name": "Updated Company",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["first_name"] == "Updated"
    assert body["data"]["company_name"] == "Updated Company"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_viewer_cannot_update_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    VIEWER does not have customers.update.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "VIEWER",
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.patch(
        f"/api/v1/customers/{customer.id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Should Not Change",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_customer_update_cannot_archive_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    customers.update must not be sufficient to archive a customer.

    Archiving requires the dedicated archive operation and therefore
    customers.delete.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "MANAGER",
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.patch(
        f"/api/v1/customers/{customer.id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "status": "archived",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Archiving a customer requires the archive operation."
    )

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ACTIVE

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# customers.delete / archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_name",
    [
        "MANAGER",
        "AGENT",
        "VIEWER",
    ],
)
async def test_roles_without_customers_delete_cannot_archive(
    role_name: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Roles without customers.delete cannot use the archive endpoint.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        role_name,
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.post(
        f"/api/v1/customers/{customer.id}/archive?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ACTIVE

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_name",
    [
        "OWNER",
        "ADMIN",
    ],
)
async def test_roles_with_customers_delete_can_archive(
    role_name: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    OWNER and ADMIN have customers.delete according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        role_name,
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
    )

    response = await client.post(
        f"/api/v1/customers/{customer.id}/archive?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(customer.id)
    assert body["data"]["status"] == "archived"

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ARCHIVED

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_cannot_restore_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    VIEWER does not have customers.update.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "VIEWER",
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
        status=CustomerStatus.ARCHIVED,
    )

    response = await client.post(
        f"/api/v1/customers/{customer.id}/restore?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ARCHIVED

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_name",
    [
        "MANAGER",
        "AGENT",
    ],
)
async def test_roles_with_customers_update_can_restore(
    role_name: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    MANAGER and AGENT have customers.update according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        role_name,
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
        status=CustomerStatus.ARCHIVED,
    )

    response = await client.post(
        f"/api/v1/customers/{customer.id}/restore?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(customer.id)
    assert body["data"]["status"] == "active"

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ACTIVE

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )