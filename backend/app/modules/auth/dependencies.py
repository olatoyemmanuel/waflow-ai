"""
WAFlow AI authentication dependencies.

FastAPI dependencies defined here are reused by protected
application endpoints.

Important multi-tenant rule:

The client does not get to establish its own tenant identity.

The JWT identifies the user. The database membership establishes
which tenants and roles that user actually has access to.
"""

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
    TenantStatus,
    User,
    UserStatus,
)

bearer_scheme = HTTPBearer(
    auto_error=False,
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Resolve the authenticated user from the JWT access token.
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


async def require_tenant_membership(
    tenant_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Membership:
    """
    Resolve and validate a user's membership in a tenant.

    Tenant and membership status are loaded eagerly so this function
    does not trigger implicit database I/O through an ORM relationship.
    """

    result = await db.execute(
        select(Membership)
        .options(
            selectinload(Membership.tenant),
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