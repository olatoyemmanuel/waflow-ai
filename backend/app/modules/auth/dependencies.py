"""
WAFlow AI authentication and authorization dependencies.

This module contains the FastAPI dependencies used to establish:

1. The authenticated user.
2. The user's active membership in a tenant.
3. The user's tenant authorization context.
4. Role-based authorization.
5. Permission-based authorization.

Multi-tenant security rule:

A client-provided tenant_id is NEVER treated as proof of tenant access.

The tenant_id only identifies which tenant the authenticated user wants
to operate against. Access is granted only when the database confirms
that the authenticated user has an ACTIVE membership in that tenant and
that the tenant itself is ACTIVE.

Authorization flow:

    JWT
      │
      ▼
    User
      │
      ▼
    Active Membership
      │
      ├── Active Tenant
      │
      └── Role
            │
            └── Permission
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.modules.auth.security import decode_access_token
from app.modules.identity.models import (
    Membership,
    MembershipStatus,
    Permission,
    RolePermission,
    TenantStatus,
    User,
    UserStatus,
)

# ---------------------------------------------------------------------------
# HTTP bearer authentication
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(
    auto_error=False,
)


# ---------------------------------------------------------------------------
# Current authenticated user
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Resolve the authenticated user from the JWT access token.

    Security guarantees:
    - A missing token produces HTTP 401.
    - An invalid/expired token produces HTTP 401.
    - A missing user produces HTTP 401.
    - A suspended/deleted user produces HTTP 403.

    The JWT contains only the user identity. Tenant identity is resolved
    from the database and is never trusted from the JWT.
    """

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    try:
        user_id = decode_access_token(
            credentials.credentials,
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from None

    result = await db.execute(
        select(User).where(
            User.id == user_id,
        ),
    )

    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account was not found.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]


# ---------------------------------------------------------------------------
# Tenant membership authorization
# ---------------------------------------------------------------------------


async def require_tenant_membership(
    tenant_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Membership:
    """
    Resolve and validate the authenticated user's tenant membership.

    The tenant_id identifies the tenant requested by the operation, but
    it does NOT grant access by itself.

    Access is granted only when all of the following are true:

    - The JWT identifies an existing active user.
    - The user has an ACTIVE membership for tenant_id.
    - The tenant itself is ACTIVE.

    Tenant and role relationships are eagerly loaded so later
    authorization checks do not trigger implicit asynchronous ORM I/O.
    """

    result = await db.execute(
        select(Membership)
        .options(
            selectinload(Membership.tenant),
            selectinload(Membership.role),
        )
        .where(
            Membership.user_id == current_user.id,
            Membership.tenant_id == tenant_id,
            Membership.status == MembershipStatus.ACTIVE,
        ),
    )

    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this tenant.",
        )

    if membership.tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This tenant is not active.",
        )

    return membership


CurrentMembership = Annotated[
    Membership,
    Depends(require_tenant_membership),
]


# ---------------------------------------------------------------------------
# Tenant authorization context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantContext:
    """
    Immutable authorization context for a tenant-scoped request.

    These values originate from the authenticated user's validated
    membership, not from untrusted frontend claims.
    """

    user_id: UUID
    tenant_id: UUID
    membership_id: UUID
    role_id: UUID
    role_name: str


async def get_tenant_context(
    current_user: CurrentUser,
    membership: CurrentMembership,
) -> TenantContext:
    """
    Build a tenant authorization context from a validated membership.
    """

    return TenantContext(
        user_id=current_user.id,
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        role_id=membership.role_id,
        role_name=membership.role.name,
    )


CurrentTenantContext = Annotated[
    TenantContext,
    Depends(get_tenant_context),
]


# ---------------------------------------------------------------------------
# Role authorization
# ---------------------------------------------------------------------------


def require_role(
    *allowed_roles: str,
):
    """
    Create a FastAPI dependency requiring one of the supplied roles.

    Example:

        OwnerContext = Annotated[
            TenantContext,
            Depends(require_role("OWNER")),
        ]

    An authenticated user without the required role receives HTTP 403.
    """

    normalized_roles = {
        role.strip().upper()
        for role in allowed_roles
        if role.strip()
    }

    if not normalized_roles:
        raise ValueError(
            "At least one role must be supplied to require_role().",
        )

    async def role_dependency(
        tenant_context: CurrentTenantContext,
    ) -> TenantContext:
        """
        Verify that the current tenant membership has an allowed role.
        """

        if tenant_context.role_name.upper() not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return tenant_context

    return role_dependency


# ---------------------------------------------------------------------------
# Permission authorization
# ---------------------------------------------------------------------------


async def _has_permission(
    db: AsyncSession,
    role_id: UUID,
    permission_name: str,
) -> bool:
    """
    Determine whether a role has a specific permission.

    The permission is resolved from the database instead of relying on
    frontend claims or hard-coded role behavior.
    """

    result = await db.execute(
        select(RolePermission.role_id)
        .join(
            Permission,
            Permission.id == RolePermission.permission_id,
        )
        .where(
            RolePermission.role_id == role_id,
            Permission.name == permission_name,
        )
        .limit(1),
    )

    return result.scalar_one_or_none() is not None


def require_permission(
    permission_name: str,
):
    """
    Create a FastAPI dependency requiring a specific permission.

    Permission names follow the established resource.action convention.

    Examples:

        require_permission("customers.read")
        require_permission("customers.create")
        require_permission("billing.manage")

    An authenticated user without the permission receives HTTP 403.
    """

    normalized_permission = permission_name.strip().lower()

    if not normalized_permission:
        raise ValueError(
            "A permission name must be supplied to require_permission().",
        )

    async def permission_dependency(
        tenant_context: CurrentTenantContext,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> TenantContext:
        """
        Verify that the current tenant role has the requested permission.
        """

        has_permission = await _has_permission(
            db=db,
            role_id=tenant_context.role_id,
            permission_name=normalized_permission,
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return tenant_context

    return permission_dependency