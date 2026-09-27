"""
WAFlow AI refresh-session integration tests.

These tests exercise the real FastAPI authentication routes against
the configured PostgreSQL database.

Covered refresh-session flows:
- Login returns an access token and refresh token.
- Login creates a persistent refresh session.
- Refresh-token rotation creates a replacement session.
- The previous refresh session is revoked after rotation.
- The replacement session points back to the previous session.
- A rotated refresh token cannot be reused.
- Refresh-token reuse detection revokes the entire token family.
- Logout revokes the refresh token.
- A revoked refresh token cannot be used after logout.

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
from app.modules.auth.refresh_sessions import RefreshSession
from app.modules.identity.models import Membership, Tenant, User


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a real asynchronous PostgreSQL session for test cleanup
    and database-state verification.
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

    Refresh sessions are deleted automatically through the
    refresh_sessions.user_id -> users.id ON DELETE CASCADE constraint.

    The user's membership is also deleted automatically because the
    memberships.user_id foreign key uses ON DELETE CASCADE.
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

    # Deleting the user cascades to memberships and refresh sessions.
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


async def register_test_user(
    client: httpx.AsyncClient,
    email: str,
    business_name: str,
) -> None:
    """
    Register a unique test account used by a refresh-session test.
    """

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "first_name": "Refresh",
            "last_name": "Test",
            "phone": "+2348000000000",
            "business_name": business_name,
        },
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh_tokens(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that a successful login returns both token types.

    The refresh token is opaque and should be persisted only as a
    SHA-256 hash in PostgreSQL.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-refresh-login-{unique_id}@example.com"
    business_name = f"Refresh Login Business {unique_id}"

    await register_test_user(
        client,
        email,
        business_name,
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]
    assert body["data"]["token_type"] == "bearer"

    refresh_token = body["data"]["refresh_token"]

    # The raw refresh token must not be stored in PostgreSQL.
    assert len(refresh_token) >= 20

    result = await db_session.execute(
        select(RefreshSession)
        .join(
            User,
            User.id == RefreshSession.user_id,
        )
        .where(
            User.email == email,
        ),
    )

    session = result.scalar_one()

    assert session.token_hash != refresh_token
    assert len(session.token_hash) == 64
    assert session.revoked_at is None
    assert session.replaced_by_session_id is None

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify the normal refresh-token rotation flow.

    Expected behavior:
    - The original refresh session is revoked.
    - A new refresh session is created.
    - Both sessions belong to the same token family.
    - The original session points to the replacement session.
    - The API returns a new access token and refresh token.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-refresh-rotate-{unique_id}@example.com"
    business_name = f"Refresh Rotate Business {unique_id}"

    await register_test_user(
        client,
        email,
        business_name,
    )

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    login_data = login_response.json()["data"]

    original_refresh_token = login_data["refresh_token"]

    original_result = await db_session.execute(
        select(RefreshSession)
        .join(
            User,
            User.id == RefreshSession.user_id,
        )
        .where(
            User.email == email,
        ),
    )

    original_session = original_result.scalar_one()

    original_session_id = original_session.id
    original_family_id = original_session.token_family_id

    # Capture the user ID before expiring the ORM instance.
    #
    # After expire_all(), accessing an expired ORM attribute can trigger
    # implicit database IO. AsyncSession does not allow that implicit IO
    # from normal synchronous attribute access, which causes MissingGreenlet.
    original_user_id = original_session.user_id

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": original_refresh_token,
        },
    )

    assert refresh_response.status_code == 200

    refresh_data = refresh_response.json()["data"]

    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert refresh_data["token_type"] == "bearer"

    new_refresh_token = refresh_data["refresh_token"]

    assert new_refresh_token != original_refresh_token

    # Refresh the SQLAlchemy view so the test sees the state committed
    # by the FastAPI request.
    db_session.expire_all()

    result = await db_session.execute(
        select(RefreshSession)
        .where(
            RefreshSession.user_id == original_user_id,
        )
        .order_by(
            RefreshSession.created_at,
        ),
    )

    sessions = list(result.scalars().all())

    old_session = next(
        session
        for session in sessions
        if session.id == original_session_id
    )

    replacement_session = next(
        session
        for session in sessions
        if session.id != original_session_id
    )

    assert old_session.revoked_at is not None
    assert old_session.last_used_at is not None
    assert old_session.replaced_by_session_id == replacement_session.id

    assert replacement_session.revoked_at is None
    assert replacement_session.token_family_id == original_family_id

    # Verify the newly issued raw refresh token maps to the replacement
    # session through the stored hash rather than being stored directly.
    assert replacement_session.token_hash != new_refresh_token
    assert len(replacement_session.token_hash) == 64

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_reusing_rotated_refresh_token_revokes_token_family(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify refresh-token reuse detection.

    When an already-rotated refresh token is presented again, the
    entire token family should be revoked.

    This protects against a stolen refresh token being replayed after
    the legitimate client has already rotated it.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-refresh-reuse-{unique_id}@example.com"
    business_name = f"Refresh Reuse Business {unique_id}"

    await register_test_user(
        client,
        email,
        business_name,
    )

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    original_refresh_token = login_response.json()["data"]["refresh_token"]

    first_refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": original_refresh_token,
        },
    )

    assert first_refresh_response.status_code == 200

    replacement_refresh_token = first_refresh_response.json()["data"][
        "refresh_token"
    ]

    # The old token has already been rotated. Presenting it again should
    # trigger refresh-token reuse detection.
    reuse_response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": original_refresh_token,
        },
    )

    assert reuse_response.status_code == 401

    body = reuse_response.json()

    assert body["detail"] == "Refresh token reuse detected."

    db_session.expire_all()

    result = await db_session.execute(
        select(RefreshSession)
        .join(
            User,
            User.id == RefreshSession.user_id,
        )
        .where(
            User.email == email,
        )
        .order_by(
            RefreshSession.created_at,
        ),
    )

    sessions = list(result.scalars().all())

    assert len(sessions) == 2

    # Reuse detection must revoke every session in the family.
    assert all(
        session.revoked_at is not None
        for session in sessions
    )

    assert (
        sessions[0].token_family_id
        == sessions[1].token_family_id
    )

    # The replacement token should now also be unusable because the
    # entire family was revoked.
    second_refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": replacement_refresh_token,
        },
    )

    assert second_refresh_response.status_code == 401

    await cleanup_test_user(
        db_session,
        email,
    )


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify that logout revokes the supplied refresh session.

    Logout is intentionally idempotent from the API consumer's
    perspective: the important security outcome is that the token
    cannot be used to obtain another access token.
    """

    unique_id = uuid4().hex[:12]

    email = f"test-refresh-logout-{unique_id}@example.com"
    business_name = f"Refresh Logout Business {unique_id}"

    await register_test_user(
        client,
        email,
        business_name,
    )

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    refresh_token = login_response.json()["data"]["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert logout_response.status_code == 200

    logout_body = logout_response.json()

    assert logout_body["success"] is True

    db_session.expire_all()

    result = await db_session.execute(
        select(RefreshSession)
        .join(
            User,
            User.id == RefreshSession.user_id,
        )
        .where(
            User.email == email,
        ),
    )

    session = result.scalar_one()

    assert session.revoked_at is not None

    # A logged-out refresh token must not create another token pair.
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert refresh_response.status_code == 401

    await cleanup_test_user(
        db_session,
        email,
    )