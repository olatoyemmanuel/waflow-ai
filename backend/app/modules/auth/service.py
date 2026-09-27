"""
WAFlow AI authentication service.

This module contains authentication business logic.

Routes should remain thin and delegate business operations
to this service layer.
"""

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.schemas import (
    CurrentUserResponse,
    RegisterRequest,
    TenantMembershipResponse,
)
from app.modules.auth.security import (
    create_access_token,
    hash_password,
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

    Example:
        acme
        acme-2
        acme-3
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

    We intentionally do not create roles during registration.
    Roles are controlled by the RBAC seed/migration system.
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

    # Flush generates the UUIDs without committing the transaction.
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

    # Suspended/deleted accounts must not authenticate.
    if user.status != UserStatus.ACTIVE:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    user.last_login_at = datetime.now(timezone.utc)

    return user


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


def create_user_access_token(user: User) -> str:
    """
    Create an access token for an authenticated user.
    """

    return create_access_token(user.id)