"""
WAFlow AI customer/CRM API schemas.

These Pydantic schemas define the API boundary for customer records.

Security rules:

- tenant_id is never accepted from client input
- id and timestamps are server-managed
- create/update payloads expose only mutable customer fields
"""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.modules.customers.models import CustomerStatus


class CustomerCreate(BaseModel):
    """
    Payload for creating a customer.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Customer first name.",
    )

    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Customer last name.",
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
        description="Customer phone number.",
    )

    email: EmailStr | None = Field(
        default=None,
        description="Customer email address.",
    )

    company_name: str | None = Field(
        default=None,
        max_length=255,
        description="Customer company or organization.",
    )

    status: CustomerStatus = Field(
        default=CustomerStatus.ACTIVE,
        description="Customer lifecycle status.",
    )

    source: str | None = Field(
        default=None,
        max_length=100,
        description="Source through which the customer was acquired.",
    )

    notes: str | None = Field(
        default=None,
        description="Internal customer notes.",
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_required_names(
        cls,
        value: str,
    ) -> str:
        """
        Reject names that become empty after whitespace normalization.
        """

        normalized = value.strip()

        if not normalized:
            raise ValueError("Name cannot be empty.")

        return normalized

    @field_validator(
        "phone",
        "company_name",
        "source",
        "notes",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize optional string fields.

        Empty strings become None.
        """

        if value is None:
            return None

        normalized = value.strip()

        return normalized or None


class CustomerUpdate(BaseModel):
    """
    Payload for partially updating a customer.

    All fields are optional because PATCH requests may modify only
    selected customer attributes.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Customer first name.",
    )

    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Customer last name.",
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
        description="Customer phone number.",
    )

    email: EmailStr | None = Field(
        default=None,
        description="Customer email address.",
    )

    company_name: str | None = Field(
        default=None,
        max_length=255,
        description="Customer company or organization.",
    )

    status: CustomerStatus | None = Field(
        default=None,
        description="Customer lifecycle status.",
    )

    source: str | None = Field(
        default=None,
        max_length=100,
        description="Source through which the customer was acquired.",
    )

    notes: str | None = Field(
        default=None,
        description="Internal customer notes.",
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_optional_names(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Reject names that become empty after whitespace normalization.
        """

        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("Name cannot be empty.")

        return normalized

    @field_validator(
        "phone",
        "company_name",
        "source",
        "notes",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize optional string fields.

        Empty strings become None.
        """

        if value is None:
            return None

        normalized = value.strip()

        return normalized or None


class CustomerResponse(BaseModel):
    """
    Public representation of a customer returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    first_name: str
    last_name: str
    phone: str | None
    email: EmailStr | None
    company_name: str | None
    status: CustomerStatus
    source: str | None
    notes: str | None
    last_contacted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    """
    Paginated customer collection response.

    This flattened pagination contract is retained for compatibility with
    the existing customer API schema and tests.

    Internally, CustomerService uses the reusable PaginationMeta object.
    The router maps that internal object into this public response shape.
    """

    items: list[CustomerResponse]

    total: int = Field(
        ge=0,
        description="Total number of matching customers.",
    )

    page: int = Field(
        ge=1,
        description="Current one-based page.",
    )

    page_size: int = Field(
        ge=1,
        description="Number of customers requested per page.",
    )

    pages: int = Field(
        ge=0,
        description="Total number of available pages.",
    )