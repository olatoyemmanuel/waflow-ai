"""
WAFlow AI authentication API routes.

Endpoints:

POST /register
POST /login
POST /refresh
POST /logout
GET  /me
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.security import create_access_token
from app.modules.auth.service import (
    RefreshTokenSecurityError,
    authenticate_user,
    build_current_user_response,
    create_refresh_session,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def get_client_ip(request: Request) -> str | None:
    """
    Return the direct client address.

    Reverse-proxy trust will be configured explicitly during deployment.

    We intentionally do not trust X-Forwarded-For here because doing so
    without a trusted proxy configuration would allow clients to spoof
    their IP address.
    """

    if request.client is None:
        return None

    return request.client.host


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Register a new WAFlow AI business."""

    try:
        user = await register_user(
            db,
            payload,
        )

        await db.commit()

    except ValueError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except (IntegrityError, RuntimeError) as exc:
        await db.rollback()

        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The account or business could not be created.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication configuration is incomplete.",
        ) from exc

    return {
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "message": (
                "Account created successfully. "
                "Please sign in to continue."
            ),
        },
    }


@router.post(
    "/login",
    response_model=dict,
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Authenticate a user and issue an access/refresh token pair."""

    user = await authenticate_user(
        db,
        str(payload.email),
        payload.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    try:
        _, refresh_token = await create_refresh_session(
            db,
            user.id,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )

        access_token = create_access_token(user.id)

        await db.commit()

    except IntegrityError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication session could not be created.",
        ) from exc

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    return {
        "success": True,
        "data": response.model_dump(),
    }


@router.post(
    "/refresh",
    response_model=dict,
)
async def refresh(
    payload: RefreshTokenRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Rotate a refresh token and issue a new token pair.

    Transaction handling is intentionally different for two cases:

    1. Unknown/invalid token:
       No security-state change occurred, so rollback is appropriate.

    2. Security event:
       A revoked token was replayed, an expired token was revoked, or
       an inactive user's session was revoked. These changes MUST be
       committed before returning HTTP 401.
    """

    try:
        (
            _user,
            access_token,
            refresh_token,
        ) = await rotate_refresh_token(
            db,
            payload.refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )

        # Successful rotation persists:
        # - old token revocation
        # - replacement session
        # - replacement relationship
        await db.commit()

    except RefreshTokenSecurityError as exc:
        # SECURITY CRITICAL:
        #
        # Do NOT rollback here.
        #
        # The service has intentionally changed security state:
        # - token family may have been revoked
        # - expired token may have been revoked
        # - inactive user's session may have been revoked
        #
        # Committing makes the revocation durable before returning 401.
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    except ValueError as exc:
        # Unknown token: no security-state mutation needs to survive.
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    return {
        "success": True,
        "data": response.model_dump(),
    }


@router.post(
    "/logout",
    response_model=dict,
)
async def logout(
    payload: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Revoke the supplied refresh session."""

    await revoke_refresh_token(
        db,
        payload.refresh_token,
    )

    await db.commit()

    return {
        "success": True,
        "data": {
            "message": "Logged out successfully.",
        },
    }


@router.get(
    "/me",
    response_model=dict,
)
async def get_me(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the authenticated user's identity and memberships."""

    response = await build_current_user_response(
        db,
        current_user.id,
    )

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated user was not found.",
        )

    return {
        "success": True,
        "data": response.model_dump(mode="json"),
    }