"""
WAFlow AI customer/CRM domain model.

Customers are tenant-owned CRM records. Every customer belongs to exactly
one tenant and must never be accessible across tenant boundaries.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class CustomerStatus(str, enum.Enum):
    """
    Lifecycle status for a tenant-owned customer.

    The enum values are explicitly persisted as lowercase strings in
    PostgreSQL so the database representation matches the API/business
    representation.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class Customer(Base):
    """
    Tenant-scoped CRM customer.

    A customer belongs to exactly one tenant. Phone and email uniqueness
    are scoped to that tenant, allowing different businesses to have
    customers with the same contact information.
    """

    __tablename__ = "customers"

    __table_args__ = (
        # A tenant cannot have two customers with the same phone number.
        # PostgreSQL permits multiple NULL values, which is desirable
        # because phone is optional.
        UniqueConstraint(
            "tenant_id",
            "phone",
            name="uq_customer_tenant_phone",
        ),
        # A tenant cannot have two customers with the same email address.
        # PostgreSQL permits multiple NULL values, which is desirable
        # because email is optional.
        UniqueConstraint(
            "tenant_id",
            "email",
            name="uq_customer_tenant_email",
        ),
        # Common tenant-scoped CRM query indexes.
        Index(
            "ix_customers_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_customers_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_customers_tenant_last_contacted_at",
            "tenant_id",
            "last_contacted_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant ownership is mandatory and enforced at the database level.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    company_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Explicitly persist enum values rather than Python enum member names.
    #
    # Python:
    #     CustomerStatus.ACTIVE
    #
    # PostgreSQL:
    #     'active'
    status: Mapped[CustomerStatus] = mapped_column(
        SqlEnum(
            CustomerStatus,
            name="customer_status",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        default=CustomerStatus.ACTIVE,
        nullable=False,
    )

    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )