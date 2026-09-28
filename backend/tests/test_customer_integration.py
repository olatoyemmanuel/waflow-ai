"""
WAFlow AI customer end-to-end integration tests.

These tests verify complete Customer API workflows against the real
PostgreSQL database.

4E.9 focuses on functional integration rather than repeating the
authorization and tenant-isolation suites already covered by:

- tests/test_customer_api.py
- tests/test_customer_tenant_isolation.py

Coverage includes:

- customer creation and PostgreSQL persistence
- customer retrieval
- customer update and persistence
- archive and restore lifecycle
- duplicate email handling
- duplicate phone handling
- request validation
- missing customer handling
- invalid UUID handling
- search behavior
- status filtering
- accurate pagination totals
- accurate pagination page counts
- empty collection pagination

All tests use the real PostgreSQL database configured for the backend.
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

    API database access is routed through a real PostgreSQL session.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a fresh database session for each API dependency call.
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
# Test identity helpers
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
    role_name: str = "OWNER",
) -> tuple[User, Tenant, Membership]:
    """
    Create an isolated test user, tenant, and active membership.
    """

    unique_id = uuid4().hex

    user = User(
        email=f"test-customer-integration-{unique_id}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        first_name="Customer",
        last_name="Integration",
        phone="+2348000000000",
        is_email_verified=True,
    )

    tenant = Tenant(
        name=f"Customer Integration Tenant {unique_id}",
        slug=f"customer-integration-{unique_id}",
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
    Remove the isolated test user and tenant.

    Customer and membership rows are removed through the configured
    foreign-key cascade relationships.
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
# Customer data helpers
# ---------------------------------------------------------------------------


async def create_test_customer(
    db_session: AsyncSession,
    tenant_id: UUID,
    *,
    first_name: str = "Integration",
    last_name: str = "Customer",
    email: str | None = None,
    phone: str | None = None,
    company_name: str = "Integration Test Company",
    status: CustomerStatus = CustomerStatus.ACTIVE,
) -> Customer:
    """
    Create a customer directly in PostgreSQL for setup-only scenarios.
    """

    unique_id = uuid4().hex

    customer = Customer(
        tenant_id=tenant_id,
        first_name=first_name,
        last_name=last_name,
        phone=phone or f"+23480{unique_id[:8]}",
        email=email or f"integration-{unique_id}@example.com",
        company_name=company_name,
        status=status,
    )

    db_session.add(customer)

    await db_session.commit()
    await db_session.refresh(customer)

    return customer


# ---------------------------------------------------------------------------
# Create integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_customer_persists_to_postgresql(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A successful API create must produce a durable PostgreSQL row.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "phone": "+2348012345001",
            "email": "ada.integration@example.com",
            "company_name": "Analytical Engines",
            "source": "integration-test",
            "notes": "Created through API.",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["first_name"] == "Ada"
    assert body["data"]["last_name"] == "Lovelace"
    assert body["data"]["email"] == "ada.integration@example.com"
    assert body["data"]["phone"] == "+2348012345001"
    assert body["data"]["company_name"] == "Analytical Engines"
    assert body["data"]["status"] == "active"

    customer_id = UUID(body["data"]["id"])

    persisted_customer = await db_session.get(
        Customer,
        customer_id,
    )

    assert persisted_customer is not None
    assert persisted_customer.tenant_id == tenant.id
    assert persisted_customer.first_name == "Ada"
    assert persisted_customer.last_name == "Lovelace"
    assert persisted_customer.email == "ada.integration@example.com"
    assert persisted_customer.phone == "+2348012345001"
    assert persisted_customer.source == "integration-test"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Read integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_customer_returns_persisted_customer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    A persisted customer must be retrievable through the API.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    customer = await create_test_customer(
        db_session,
        tenant.id,
        first_name="Persisted",
        last_name="Customer",
    )

    response = await client.get(
        f"/api/v1/customers/{customer.id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["id"] == str(customer.id)
    assert body["data"]["first_name"] == "Persisted"
    assert body["data"]["last_name"] == "Customer"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Complete lifecycle integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_complete_lifecycle(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Exercise the full customer lifecycle through the API:

        create
          ↓
        read
          ↓
        update
          ↓
        archive
          ↓
        restore
          ↓
        read

    The database is checked after each mutation.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    create_response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Lifecycle",
            "last_name": "Customer",
            "email": "lifecycle@example.com",
            "phone": "+2348012345002",
        },
    )

    assert create_response.status_code == 201

    customer_id = UUID(
        create_response.json()["data"]["id"],
    )

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    get_response = await client.get(
        f"/api/v1/customers/{customer_id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["status"] == "active"

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    update_response = await client.patch(
        f"/api/v1/customers/{customer_id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Updated",
            "company_name": "Updated Company",
            "notes": "Updated through lifecycle test.",
        },
    )

    assert update_response.status_code == 200

    update_body = update_response.json()

    assert update_body["data"]["first_name"] == "Updated"
    assert update_body["data"]["company_name"] == "Updated Company"

    customer = await db_session.get(
        Customer,
        customer_id,
    )

    assert customer is not None

    await db_session.refresh(customer)

    assert customer.first_name == "Updated"
    assert customer.company_name == "Updated Company"
    assert customer.status == CustomerStatus.ACTIVE

    # ---------------------------------------------------------
    # Archive
    # ---------------------------------------------------------

    archive_response = await client.post(
        f"/api/v1/customers/{customer_id}/archive"
        f"?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["status"] == "archived"

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ARCHIVED

    # ---------------------------------------------------------
    # Restore
    # ---------------------------------------------------------

    restore_response = await client.post(
        f"/api/v1/customers/{customer_id}/restore"
        f"?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["data"]["status"] == "active"

    await db_session.refresh(customer)

    assert customer.status == CustomerStatus.ACTIVE

    # ---------------------------------------------------------
    # Final read
    # ---------------------------------------------------------

    final_response = await client.get(
        f"/api/v1/customers/{customer_id}?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert final_response.status_code == 200

    final_body = final_response.json()

    assert final_body["data"]["first_name"] == "Updated"
    assert final_body["data"]["company_name"] == "Updated Company"
    assert final_body["data"]["status"] == "active"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Duplicate constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_email_returns_conflict(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Duplicate customer email inside one tenant must return HTTP 409.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    await create_test_customer(
        db_session,
        tenant.id,
        email="duplicate@example.com",
        phone="+2348012345101",
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Duplicate",
            "last_name": "Email",
            "email": "duplicate@example.com",
            "phone": "+2348012345102",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A customer with this email already exists."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_duplicate_phone_returns_conflict(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Duplicate customer phone inside one tenant must return HTTP 409.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    await create_test_customer(
        db_session,
        tenant.id,
        email="existing-phone@example.com",
        phone="+2348012345201",
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Duplicate",
            "last_name": "Phone",
            "email": "different@example.com",
            "phone": "+2348012345201",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A customer with this phone number already exists."
    )

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Validation integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_customer_payload_returns_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Invalid API payloads must be rejected before persistence.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "",
            "last_name": "Customer",
            "email": "not-an-email",
        },
    )

    assert response.status_code == 422

    # The invalid request must not create a customer row.
    result = await db_session.execute(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
        ),
    )

    customers = list(result.scalars().all())

    assert customers == []

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_unknown_customer_field_returns_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    CustomerCreate uses extra='forbid', so unsupported fields must be
    rejected at the API boundary.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    response = await client.post(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
        json={
            "first_name": "Extra",
            "last_name": "Field",
            "unknown_field": "must-be-rejected",
        },
    )

    assert response.status_code == 422

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_invalid_customer_uuid_returns_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    FastAPI must reject an invalid customer UUID at request validation.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    response = await client.get(
        f"/api/v1/customers/not-a-uuid?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 422

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Missing resource integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("get", ""),
        ("patch", ""),
        ("post", "/archive"),
        ("post", "/restore"),
    ],
)
async def test_missing_customer_returns_404(
    method: str,
    path_suffix: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Missing customer IDs must return HTTP 404 consistently across the
    customer resource operations.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    missing_customer_id = uuid4()

    url = (
        f"/api/v1/customers/{missing_customer_id}"
        f"{path_suffix}?tenant_id={tenant.id}"
    )

    if method == "get":
        response = await client.get(
            url,
            headers=authorization_headers(user.id),
        )

    elif method == "patch":
        response = await client.patch(
            url,
            headers=authorization_headers(user.id),
            json={
                "first_name": "Missing",
            },
        )

    else:
        response = await client.post(
            url,
            headers=authorization_headers(user.id),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


# ---------------------------------------------------------------------------
# Search and pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_accurate_total_and_pages(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Search pagination must report the total number of matching records,
    not merely the size of the current page.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    for index in range(5):
        await create_test_customer(
            db_session,
            tenant.id,
            first_name=f"Searchable{index}",
            company_name="Search Company",
        )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant.id}"
        "&search=Searchable&page=2&page_size=2",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["total"] == 5
    assert body["data"]["page"] == 2
    assert body["data"]["page_size"] == 2
    assert body["data"]["pages"] == 3
    assert len(body["data"]["items"]) == 2

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_status_filter_returns_accurate_total(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Status filtering must report the total number of matching customers.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    for index in range(3):
        await create_test_customer(
            db_session,
            tenant.id,
            first_name=f"Active{index}",
            status=CustomerStatus.ACTIVE,
        )

    await create_test_customer(
        db_session,
        tenant.id,
        first_name="Inactive",
        status=CustomerStatus.INACTIVE,
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant.id}"
        "&status=active&page=1&page_size=2",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["total"] == 3
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 2
    assert body["data"]["pages"] == 2
    assert len(body["data"]["items"]) == 2

    for item in body["data"]["items"]:
        assert item["status"] == "active"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_empty_customer_collection_has_zero_pages(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    An empty customer collection must report total=0 and pages=0.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant.id}",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 20
    assert body["data"]["pages"] == 0

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )


@pytest.mark.asyncio
async def test_empty_search_behaves_like_normal_list(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    An empty search value must behave like a normal customer listing.
    """

    user, tenant, _ = await create_test_identity(
        db_session,
    )

    await create_test_customer(
        db_session,
        tenant.id,
        first_name="Empty",
        last_name="Search",
    )

    response = await client.get(
        f"/api/v1/customers?tenant_id={tenant.id}&search=",
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["total"] == 1
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["first_name"] == "Empty"

    await cleanup_test_identity(
        db_session,
        user.id,
        tenant.id,
    )