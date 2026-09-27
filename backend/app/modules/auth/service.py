"""
WAFlow AI authentication service.

This module contains authentication business logic.

Routes remain thin and delegate authentication operations to this
service layer.

Refresh-token security:

1. Login creates a refresh-token family.
2. Only the token hash is stored.
3. Every successful refresh revokes the current session.
4. A replacement session is created.
5. Reuse of a revoked token revokes the entire token family.
6. Security-related revocations are committed by the router before
   returning an authentication error.
"""

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.refresh_sessions import RefreshSession
from app.modules.auth.schemas import (
    CurrentUserResponse,
    RegisterRequest,
    TenantMembershipResponse,
)
from app.modules.auth.security import (
    create_access_token,
    create_refresh_token,
    get_refresh_token_expiry,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.identity.models import (
    Membership,
    MembershipStatus,
    Role,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)


class RefreshTokenSecurityError(ValueError):
    """
    Authentication error that also represents a security-state change.

    Examples:
    - Refresh-token reuse detected.
    - Expired refresh token revoked.
    - Refresh token belonging to an inactive user revoked.

    The caller must COMMIT these changes before returning the HTTP error.
    Rolling them back would undo the security revocation.
    """


def normalize_email(email: str) -> str:
    """
    Normalize an email address before persistence and lookup.
    """

    return email.strip().lower()


def generate_slug(name: str) -> str:
    """
    Generate a basic URL-safe tenant slug.

    Example:
        "Acme Properties Ltd" → "acme-properties-ltd"
    """

    slug = name.strip().lower()

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        slug,
    )

    slug = slug.strip("-")

    return slug or "business"


async def get_unique_tenant_slug(
    db: AsyncSession,
    business_name: str,
) -> str:
    """
    Generate a tenant slug and resolve collisions.
    """

    base_slug = generate_slug(business_name)

    candidate = base_slug
    suffix = 2

    while True:
        result = await db.execute(
            select(Tenant.id).where(
                Tenant.slug == candidate,
            ),
        )

        if result.scalar_one_or_none() is None:
            return candidate

        candidate = f"{base_slug}-{suffix}"
        suffix += 1


async def get_owner_role(
    db: AsyncSession,
) -> Role:
    """
    Retrieve the existing OWNER role seeded by the RBAC system.
    """

    result = await db.execute(
        select(Role).where(
            Role.name == "OWNER",
        ),
    )

    role = result.scalar_one_or_none()

    if role is None:
        raise RuntimeError(
            "OWNER role has not been seeded.",
        )

    return role


async def register_user(
    db: AsyncSession,
    payload: RegisterRequest,
) -> User:
    """
    Create a new user, tenant, and OWNER membership atomically.

    The database transaction is controlled by the caller.
    """

    email = normalize_email(str(payload.email))

    existing_user = await db.execute(
        select(User.id).where(
            User.email == email,
        ),
    )

    if existing_user.scalar_one_or_none() is not None:
        raise ValueError(
            "An account with this email already exists.",
        )

    owner_role = await get_owner_role(db)

    tenant_slug = await get_unique_tenant_slug(
        db,
        payload.business_name,
    )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        is_email_verified=False,
        status=UserStatus.ACTIVE,
    )

    tenant = Tenant(
        name=payload.business_name,
        slug=tenant_slug,
        timezone="Africa/Lagos",
        currency="NGN",
        status=TenantStatus.ACTIVE,
    )

    db.add(user)
    db.add(tenant)

    await db.flush()

    membership = Membership(
        user_id=user.id,
        tenant_id=tenant.id,
        role_id=owner_role.id,
        status=MembershipStatus.ACTIVE,
    )

    db.add(membership)

    await db.flush()

    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """
    Authenticate a user by email and password.

    Returns None for invalid credentials or inactive users.
    """

    normalized_email = normalize_email(email)

    result = await db.execute(
        select(User).where(
            User.email == normalized_email,
        ),
    )

    user = result.scalar_one_or_none()

    if user is None:
        return None

    if user.status != UserStatus.ACTIVE:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    user.last_login_at = datetime.now(timezone.utc)

    return user


async def create_refresh_session(
    db: AsyncSession,
    user_id: UUID,
    token_family_id: UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[RefreshSession, str]:
    """
    Create a refresh session and return:

        (database session, plaintext refresh token)

    Only the SHA-256 hash is stored in PostgreSQL.
    """

    refresh_token = create_refresh_token()

    session = RefreshSession(
        user_id=user_id,
        token_hash=hash_refresh_token(refresh_token),
        token_family_id=token_family_id or uuid4(),
        expires_at=get_refresh_token_expiry(),
        user_agent=user_agent,
        ip_address=ip_address,
    )

    db.add(session)

    await db.flush()

    return session, refresh_token


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """
    Issue an access token and a new refresh token.

    A new login always starts a new refresh-token family.
    """

    access_token = create_access_token(user.id)

    _, refresh_token = await create_refresh_session(
        db,
        user.id,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return access_token, refresh_token


async def rotate_refresh_token(
    db: AsyncSession,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str, str]:
    """
    Validate and rotate a refresh token.

    Returns:
        user, new_access_token, new_refresh_token

    Security behavior:
    - Unknown token → reject without a database security-state change.
    - Expired token → revoke it and reject.
    - Active token → rotate normally.
    - Revoked/reused token → revoke the entire token family and reject.

    The caller controls the final transaction commit.
    """

    token_hash = hash_refresh_token(refresh_token)

    result = await db.execute(
        select(RefreshSession)
        .where(
            RefreshSession.token_hash == token_hash,
        )
        .with_for_update(),
    )

    session = result.scalar_one_or_none()

    # An unknown token cannot be associated with a token family.
    # There is therefore no security-state change to persist.
    if session is None:
        raise ValueError(
            "Invalid refresh token.",
        )

    now = datetime.now(timezone.utc)

    # A revoked token being presented again indicates possible
    # refresh-token replay/reuse.
    #
    # IMPORTANT:
    # The family revocation must survive the HTTP 401 response.
    # Therefore we raise RefreshTokenSecurityError rather than the
    # ordinary ValueError used for unknown tokens.
    if session.revoked_at is not None:
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_family_id
                == session.token_family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
            ),
        )

        raise RefreshTokenSecurityError(
            "Refresh token reuse detected.",
        )

    # Expired tokens are explicitly revoked so they cannot later
    # become valid through an application bug or clock issue.
    if session.expires_at <= now:
        session.revoked_at = now

        raise RefreshTokenSecurityError(
            "Refresh token has expired.",
        )

    user_result = await db.execute(
        select(User).where(
            User.id == session.user_id,
        ),
    )

    user = user_result.scalar_one_or_none()

    # If the account is no longer active, revoke the refresh session.
    if user is None or user.status != UserStatus.ACTIVE:
        session.revoked_at = now

        raise RefreshTokenSecurityError(
            "User account is not active.",
        )

    # Generate the replacement token before updating the old session
    # so the replacement relationship can be persisted atomically.
    new_refresh_token = create_refresh_token()

    replacement_session = RefreshSession(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_token),
        token_family_id=session.token_family_id,
        expires_at=get_refresh_token_expiry(),
        user_agent=user_agent,
        ip_address=ip_address,
    )

    db.add(replacement_session)

    await db.flush()

    # Rotate the old session.
    #
    # revoked_at prevents the old token from being used again.
    # replaced_by_session_id provides an audit trail of rotation.
    session.revoked_at = now
    session.last_used_at = now
    session.replaced_by_session_id = replacement_session.id

    new_access_token = create_access_token(user.id)

    return (
        user,
        new_access_token,
        new_refresh_token,
    )


async def revoke_refresh_token(
    db: AsyncSession,
    refresh_token: str,
) -> bool:
    """
    Revoke a refresh session.

    Returns True when an active session was revoked.

    Logout is intentionally idempotent: an unknown or already revoked
    token does not reveal additional session information.
    """

    token_hash = hash_refresh_token(refresh_token)

    result = await db.execute(
        select(RefreshSession)
        .where(
            RefreshSession.token_hash == token_hash,
        )
        .with_for_update(),
    )

    session = result.scalar_one_or_none()

    if session is None:
        return False

    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)

        return True

    return False


async def build_current_user_response(
    db: AsyncSession,
    user_id: UUID,
) -> CurrentUserResponse | None:
    """
    Load the authenticated user and all active/invited memberships.

    Tenant information is resolved from the database instead of
    being trusted from the frontend.
    """

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.memberships)
            .selectinload(Membership.tenant),
            selectinload(User.memberships)
            .selectinload(Membership.role),
        )
        .where(User.id == user_id),
    )

    user = result.scalar_one_or_none()

    if user is None:
        return None

    memberships = []

    for membership in user.memberships:
        if membership.status not in {
            MembershipStatus.ACTIVE,
            MembershipStatus.INVITED,
        }:
            continue

        if membership.tenant.status != TenantStatus.ACTIVE:
            continue

        memberships.append(
            TenantMembershipResponse(
                tenant_id=membership.tenant.id,
                tenant_name=membership.tenant.name,
                tenant_slug=membership.tenant.slug,
                role=membership.role.name,
                membership_status=membership.status.value,
            ),
        )

    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        is_email_verified=user.is_email_verified,
        status=user.status.value,
        memberships=memberships,
    )