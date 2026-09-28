"""
WAFlow AI customer security hardening tests.

4E.10 covers:
- archived status cannot be supplied during customer creation
- archived creation is rejected for roles that otherwise have create access
- pagination page numbers are bounded
- customer notes are bounded
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.pagination import MAX_PAGE, PaginationParams
from app.main import app
from app.modules.auth.security import create_access_token, hash_password
from app.modules.customers.models import Customer
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate
from app.modules.identity.models import (
    Membership,
    MembershipStatus,
    Role,
    Tenant,
    User,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a real asynchronous PostgreSQL session."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an HTTP client for the real FastAPI application."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


async def get_role(
    db_session: AsyncSession,
    role_name: str,
) -> Role:
    """Resolve a seeded role."""
    result = await db_session.execute(
        select(Role).where(Role.name == role_name),
    )

    role = result.scalar_one_or_none()

    assert role is not None, (
        f"Required seeded role {role_name!r} does not exist."
    )

    return role


async def create_test_identity(
    db_session: AsyncSession,
    role_name: str,
) -> tuple[User, Tenant]:
    """Create an isolated test user, tenant, and membership."""

    unique_id = uuid4().hex

    user = User(
        email=f"test-security-{unique_id}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        first_name="Security",
        last_name="Test",
        phone=f"+23481{unique_id[:9]}",
        is_email_verified=True,
    )

    tenant = Tenant(
        name=f"Security Test Tenant {unique_id}",
        slug=f"security-{unique_id}",
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

    return user, tenant


async def cleanup_test_identity(
    db_session: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    """Remove the test identity and tenant."""

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
    """Create a bearer authorization header."""

    token = create_access_token(user_id)

    return {
        "Authorization": f"Bearer {token}",
    }


def valid_customer_payload(
    *,
    email: str,
) -> dict[str, str]:
    """Build a minimal valid customer creation payload."""

    return {
        "first_name": "Security",
        "last_name": "Customer",
        "email": email,
        "phone": f"+23482{uuid4().hex[:9]}",
    }


def test_customer_create_schema_rejects_archived_status() -> None:
    """
    ARCHIVED must not be accepted as an initial customer status.
    """

    with pytest.raises(ValidationError):
        CustomerCreate(
            first_name="Security",
            last_name="Customer",
            status="archived",
        )


def test_customer_update_schema_enforces_notes_limit() -> None:
    """
    Customer notes must have a bounded application payload size.
    """

    with pytest.raises(ValidationError):
        CustomerUpdate(
            notes="x" * 10_001,
        )


def test_pagination_rejects_page_above_security_limit() -> None:
    """
    Pagination must reject excessively large page numbers.
    """

    with pytest.raises(ValidationError):
        PaginationParams(
            page=MAX_PAGE + 1,
        )


def test_pagination_accepts_security_limit() -> None:
    """
    The configured maximum page remains valid.
    """

    pagination = PaginationParams(
        page=MAX_PAGE,
    )

    assert pagination.page == MAX_PAGE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_name",
    [
        "MANAGER",
        "AGENT",
    ],
)
async def test_roles_with_create_permission_cannot_create_archived_customer(
    role_name: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Having customers.create must not allow direct creation of an archived
    customer. Archiving requires the dedicated archive operation.
    """

    user, tenant = await create_test_identity(
        db_session,
        role_name,
    )

    email = f"archived-at-create-{uuid4().hex}@example.com"

    payload = valid_customer_payload(
        email=email,
    )

    payload["status"] = "archived"

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json=payload,
    )

    assert response.status_code == 422

    result = await db_session.execute(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            Customer.email == email,
        ),
    )

    assert result.scalar_one_or_none() is None

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )