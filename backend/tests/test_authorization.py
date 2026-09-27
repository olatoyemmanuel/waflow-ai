"""
WAFlow AI authorization integration tests.

These tests verify the security boundaries introduced by Milestone 4C:

- Missing authentication returns HTTP 401.
- Invalid authentication returns HTTP 401.
- Active users can access their active tenant membership.
- Users cannot access another tenant.
- Suspended memberships are rejected.
- Suspended tenants are rejected.
- Role authorization returns HTTP 403 when the role is insufficient.
- Permission authorization returns HTTP 403 when the permission is missing.
- Allowed permissions are accepted.
- Tenant context comes from the authenticated membership.

The tests use the real PostgreSQL database configured for the backend.
Each test creates isolated users and tenants and removes them afterward.
"""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.modules.auth.dependencies import (
    CurrentUser,
    TenantContext,
    get_tenant_context,
    require_permission,
    require_role,
)
from app.modules.auth.security import create_access_token, hash_password
from app.modules.identity.models import (
    Membership,
    MembershipStatus,
    Role,
    Tenant,
    TenantStatus,
    User,
)

# ---------------------------------------------------------------------------
# Reusable authorization dependency aliases
# ---------------------------------------------------------------------------

OwnerTenantContext = Annotated[
    TenantContext,
    Depends(require_role("OWNER")),
]

CustomersReadTenantContext = Annotated[
    TenantContext,
    Depends(require_permission("customers.read")),
]

BillingChangePlanTenantContext = Annotated[
    TenantContext,
    Depends(require_permission("billing.change_plan")),
]


# ---------------------------------------------------------------------------
# Test application
# ---------------------------------------------------------------------------

authorization_router = APIRouter(
    prefix="/test-authorization",
)


@authorization_router.get("/authenticated")
async def authenticated_endpoint(
    current_user: CurrentUser,
) -> dict[str, object]:
    """
    Endpoint protected only by authentication.
    """

    return {
        "success": True,
        "data": {
            "user_id": str(current_user.id),
        },
    }


@authorization_router.get("/tenant")
async def tenant_endpoint(
    tenant_context: Annotated[
        TenantContext,
        Depends(get_tenant_context),
    ],
) -> dict[str, object]:
    """
    Endpoint protected by tenant membership.
    """

    return {
        "success": True,
        "data": {
            "user_id": str(tenant_context.user_id),
            "tenant_id": str(tenant_context.tenant_id),
            "membership_id": str(tenant_context.membership_id),
            "role": tenant_context.role_name,
        },
    }


@authorization_router.get("/owner")
async def owner_endpoint(
    tenant_context: OwnerTenantContext,
) -> dict[str, object]:
    """
    Endpoint requiring the OWNER role.
    """

    return {
        "success": True,
        "data": {
            "role": tenant_context.role_name,
        },
    }


@authorization_router.get("/customers-read")
async def customers_read_endpoint(
    tenant_context: CustomersReadTenantContext,
) -> dict[str, object]:
    """
    Endpoint requiring customers.read.
    """

    return {
        "success": True,
        "data": {
            "role": tenant_context.role_name,
            "permission": "customers.read",
        },
    }


@authorization_router.get("/billing-change-plan")
async def billing_change_plan_endpoint(
    tenant_context: BillingChangePlanTenantContext,
) -> dict[str, object]:
    """
    Endpoint requiring billing.change_plan.

    This permission is useful for testing the distinction between OWNER
    and ADMIN because the RBAC seed gives it only to OWNER.
    """

    return {
        "success": True,
        "data": {
            "role": tenant_context.role_name,
            "permission": "billing.change_plan",
        },
    }


authorization_app = FastAPI(
    title="WAFlow AI Authorization Test Application",
)

authorization_app.include_router(
    authorization_router,
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
    Provide an HTTPX client for the test-only FastAPI application.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """
        Use a real PostgreSQL session for dependency resolution.
        """

        async with AsyncSessionLocal() as session:
            yield session

    authorization_app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(
        app=authorization_app,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    authorization_app.dependency_overrides.clear()


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
    Create a unique user, tenant, and membership for authorization tests.
    """

    unique_id = uuid4().hex

    user = User(
        email=f"test-authz-{unique_id}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        first_name="Authorization",
        last_name="Test",
        phone="+2348000000000",
        is_email_verified=True,
    )

    tenant = Tenant(
        name=f"Authorization Test Tenant {unique_id}",
        slug=f"authz-test-{unique_id}",
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


async def cleanup_test_identity(
    db_session: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    """
    Remove the test user and tenant.

    Memberships are removed through database foreign-key cascade rules.
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
    Create a valid Authorization header for a test user.
    """

    token = create_access_token(
        user_id,
    )

    return {
        "Authorization": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_authentication_returns_401(
    client: httpx.AsyncClient,
) -> None:
    """
    Protected endpoints must reject requests without a bearer token.
    """

    response = await client.get(
        "/test-authorization/authenticated",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


@pytest.mark.asyncio
async def test_invalid_authentication_returns_401(
    client: httpx.AsyncClient,
) -> None:
    """
    Invalid access tokens must not reach authorization checks.
    """

    response = await client.get(
        "/test-authorization/authenticated",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid or expired access token."
    )


# ---------------------------------------------------------------------------
# Tenant authorization tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_tenant_membership_is_authorized(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    An active user with an active membership can access that tenant.
    """

    user, tenant, membership = await create_test_identity(
        db_session,
        "AGENT",
    )

    response = await client.get(
        f"/test-authorization/tenant?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["user_id"] == str(user.id)
    assert body["data"]["tenant_id"] == str(tenant.id)
    assert body["data"]["membership_id"] == str(membership.id)
    assert body["data"]["role"] == "AGENT"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_user_cannot_access_another_tenant(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A valid authenticated user cannot access a tenant in which they
    have no active membership.
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
        f"/test-authorization/tenant?tenant_id={other_tenant.id}",
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


@pytest.mark.asyncio
async def test_suspended_membership_returns_403(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A suspended membership cannot access its tenant.
    """

    user, tenant, membership = await create_test_identity(
        db_session,
        "AGENT",
    )

    membership.status = MembershipStatus.SUSPENDED

    await db_session.commit()

    response = await client.get(
        f"/test-authorization/tenant?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have access to this tenant."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_suspended_tenant_returns_403(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    An active membership cannot bypass a suspended tenant.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    tenant.status = TenantStatus.SUSPENDED

    await db_session.commit()

    response = await client.get(
        f"/test-authorization/tenant?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "This tenant is not active."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Role authorization tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_role_is_authorized(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    OWNER can access an OWNER-only endpoint.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "OWNER",
    )

    response = await client.get(
        f"/test-authorization/owner?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "OWNER"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_agent_is_rejected_from_owner_endpoint(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    AGENT must not pass an OWNER-only role check.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    response = await client.get(
        f"/test-authorization/owner?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
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
# Permission authorization tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_can_use_customers_read_permission(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    AGENT has customers.read according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    response = await client.get(
        f"/test-authorization/customers-read?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["role"] == "AGENT"
    assert body["data"]["permission"] == "customers.read"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_agent_is_rejected_from_billing_change_plan(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    AGENT does not have billing.change_plan.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "AGENT",
    )

    response = await client.get(
        f"/test-authorization/billing-change-plan?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
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
async def test_owner_can_use_billing_change_plan_permission(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    OWNER has billing.change_plan according to the RBAC seed.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
        "OWNER",
    )

    response = await client.get(
        f"/test-authorization/billing-change-plan?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["role"] == "OWNER"
    assert body["data"]["permission"] == "billing.change_plan"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )