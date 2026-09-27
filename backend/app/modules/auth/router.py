"""
WAFlow AI authentication API routes.

Endpoints:

POST /register
POST /login
GET  /me
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import (
    authenticate_user,
    build_current_user_response,
    create_user_access_token,
    register_user,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Register a new WAFlow AI business.

    The operation creates:
    - User
    - Tenant
    - OWNER membership

    All three belong to the same database transaction.
    """

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

        # IntegrityError is intentionally mapped to a generic
        # conflict instead of exposing database internals.
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Authenticate a user and issue an access token.
    """

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

    await db.commit()

    access_token = create_user_access_token(user)

    response = TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )

    return {
        "success": True,
        "data": response.model_dump(),
    }


@router.get(
    "/me",
    response_model=dict,
)
async def get_me(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Return the authenticated user's identity and tenant memberships.
    """

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