"""
WAFlow AI authentication integration tests.

These tests exercise the real FastAPI authentication routes against
the configured PostgreSQL database.

Covered flows:
- User/business registration
- Duplicate email protection
- Successful login
- Invalid password rejection
- Authenticated /me request
- Missing authentication rejection
- Invalid JWT rejection
- Tenant membership resolution

Each test creates a unique test account.

Test records are explicitly cleaned up after the test so that repeated
test runs do not pollute the development database.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.main import app
from app.modules.identity.models import Membership, Tenant, User


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a real asynchronous PostgreSQL session for test cleanup.

    The FastAPI application creates its own database sessions through
    the normal get_db dependency. This separate session is used only
    to remove records created by the test.
    """

    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Create an HTTPX client connected directly to the FastAPI app.

    ASGITransport allows the tests to call the FastAPI application
    without starting another Uvicorn process.
    """

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


async def cleanup_test_user(
    db_session: AsyncSession,
    email: str,
) -> None:
    """
    Remove the test user and the tenant created during registration.

    The user's membership is deleted automatically because the
    memberships.user_id foreign key uses ON DELETE CASCADE.

    We first capture the tenant ID associated with the user. After
    deleting the user, we delete only that specific tenant.

    This prevents the tests from accidentally deleting unrelated
    development data.
    """

    result = await db_session.execute(
        select(
            User.id,
            Membership.tenant_id,
        )
        .join(
            Membership,
            Membership.user_id == User.id,
        )
        .where(
            User.email == email,
        ),
    )

    record = result.first()

    if record is None:
        return

    user_id = record[0]
    tenant_id = record[1]

    # Deleting the user cascades to its membership.
    user = await db_session.get(
        User,
        user_id,
    )

    if user is not None:
        await db_session.delete(user)

    await db_session.flush()

    # Delete only the tenant belonging to this test account.
    tenant = await db_session.get(
        Tenant,
        tenant_id,
    )

    if tenant is not None:
        await db_session.delete(tenant)

    await db_session.commit()


@pytest.mark.asyncio
async def test_register_creates_user_tenant_and_owner_membership(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that registration creates the complete tenant foundation.

    Expected result:
    - HTTP 201
    - User created
    - Tenant created
    - OWNER membership created
    - Membership is ACTIVE
    """

    unique_id = uuid4().hex[:12]

    email = f"test-register-{unique_id}@example.com"
    business_name = f"Test Business {unique_id}"

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "first_name": "Test",
            "last_name": "Owner",
            "phone": "+2348000000000",
            "business_name": business_name,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["data"]["email"] == email
    assert body["data"]["first_name"] == "Test"
    assert body["data"]["last_name"] == "Owner"
    assert "id" in body["data"]

    # Authenticate the newly created account to verify that the
    # registration transaction created usable authentication data.
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["data"]["access_token"]

    # Resolve the authenticated identity and tenant membership.
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert me_response.status_code == 200

    me_body = me_response.json()

    assert me_body["success"] is True
    assert me_body["data"]["email"] == email
    assert len(me_body["data"]["memberships"]) == 1

    membership = me_body["data"]["memberships"][0]

    assert membership["tenant_name"] == business_name
    assert membership["tenant_slug"] == business_name.lower().replace(
        " ",
        "-",
    )
    assert membership["role"] == "OWNER"
    assert membership["membership_status"] == "active"

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that an existing email cannot register another account.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-duplicate-{unique_id}@example.com"

    payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Duplicate",
        "last_name": "Test",
        "phone": "+2348000000000",
        "business_name": f"Duplicate Business {unique_id}",
    }

    first_response = await client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert second_response.status_code == 409

    body = second_response.json()

    assert body["detail"] == (
        "An account with this email already exists."
    )

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that an incorrect password cannot authenticate.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-password-{unique_id}@example.com"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "first_name": "Password",
            "last_name": "Test",
            "business_name": f"Password Business {unique_id}",
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123!",
        },
    )

    assert login_response.status_code == 401

    body = login_response.json()

    assert body["detail"] == "Invalid email or password."

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_me_requires_authentication(
    client: httpx.AsyncClient,
) -> None:
    """
    Verify that /me rejects requests without a bearer token.
    """

    response = await client.get(
        "/api/v1/auth/me",
    )

    assert response.status_code == 401

    body = response.json()

    assert body["detail"] == "Authentication required."


@pytest.mark.asyncio
async def test_me_rejects_invalid_token(
    client: httpx.AsyncClient,
) -> None:
    """
    Verify that /me rejects malformed or invalid JWTs.
    """

    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401

    body = response.json()

    assert body["detail"] == "Invalid or expired access token."


@pytest.mark.asyncio
async def test_me_returns_authenticated_user_and_tenant_membership(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that a valid JWT resolves the user and database membership.

    This is particularly important for WAFlow AI's multi-tenant
    security model.

    The tenant relationship comes from PostgreSQL membership data,
    rather than from a tenant ID supplied by the client.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-me-{unique_id}@example.com"
    business_name = f"Me Business {unique_id}"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "first_name": "Current",
            "last_name": "User",
            "phone": "+2348000000000",
            "business_name": business_name,
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["data"]["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert me_response.status_code == 200

    body = me_response.json()

    assert body["success"] is True

    user = body["data"]

    assert user["email"] == email
    assert user["first_name"] == "Current"
    assert user["last_name"] == "User"
    assert user["status"] == "active"
    assert user["is_email_verified"] is False

    assert len(user["memberships"]) == 1

    membership = user["memberships"][0]

    assert membership["tenant_name"] == business_name
    assert membership["tenant_slug"] == business_name.lower().replace(
        " ",
        "-",
    )
    assert membership["role"] == "OWNER"
    assert membership["membership_status"] == "active"

    await cleanup_test_user(
        db_session,
        email,
    )
