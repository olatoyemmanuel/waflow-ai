"""
WAFlow AI authentication security utilities.

Responsibilities:
- Password hashing
- Password verification
- JWT access-token creation
- JWT access-token decoding

Security note:
JWTs are signed, not encrypted. Therefore we only place
non-sensitive identifiers in the token payload.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

# pwdlib's recommended configuration currently uses Argon2.
password_hash = PasswordHash.recommended()

settings = get_settings()

# Explicitly define the JWT algorithm so token creation and
# verification cannot accidentally use different algorithms.
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """
    Hash a plaintext password.

    The plaintext password must never be stored in the database.
    """

    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plaintext password against its stored hash.
    """

    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(user_id: UUID) -> str:
    """
    Create a short-lived JWT access token.

    The subject contains only the user ID.

    Tenant identity is deliberately NOT trusted from the JWT.
    Tenant membership must be resolved from the database.
    """

    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> UUID:
    """
    Validate and decode an access token.

    Returns:
        UUID: authenticated user ID

    Raises:
        jwt.InvalidTokenError:
            When the token is invalid, expired, malformed,
            or has an unexpected token type.
    """

    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
    )

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError(
            "Invalid token type.",
        )

    subject = payload.get("sub")

    if not subject:
        raise jwt.InvalidTokenError(
            "Token subject is missing.",
        )

    try:
        return UUID(subject)
    except ValueError as exc:
        raise jwt.InvalidTokenError(
            "Token subject is invalid.",
        ) from exc