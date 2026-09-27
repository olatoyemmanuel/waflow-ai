"""
WAFlow AI authentication schemas.

These Pydantic models define the public request and response
contracts for authentication endpoints.

Important:
- Passwords are accepted only on input.
- Password hashes are never returned through the API.
- UUIDs are represented as strings in the JSON API.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """
    Payload used to create the first user and tenant.

    Registration creates:
    1. User
    2. Tenant
    3. OWNER membership
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    phone: str | None = Field(default=None, max_length=30)

    business_name: str = Field(min_length=2, max_length=255)


class LoginRequest(BaseModel):
    """
    Credentials used to authenticate an existing user.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """
    Authentication token response.

    The refresh token will be persisted and rotated in the
    refresh-session milestone. For this milestone we establish
    the access-token contract.
    """

    access_token: str
    token_type: str = "bearer"


class TenantMembershipResponse(BaseModel):
    """
    Tenant membership visible to the authenticated user.
    """

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: str
    membership_status: str


class CurrentUserResponse(BaseModel):
    """
    Current authenticated user plus tenant memberships.

    No password or password hash is ever exposed.
    """

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None
    is_email_verified: bool
    status: str

    memberships: list[TenantMembershipResponse]