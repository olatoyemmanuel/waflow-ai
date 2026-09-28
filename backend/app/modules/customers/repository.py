"""
Customer/CRM repository.

This repository provides persistence operations for tenant-owned
Customer records.

Security boundary:

    The repository receives an already-authorized tenant_id.

    Every read, update, and delete operation includes that tenant scope.

    The tenant_id is never taken from request payloads or customer data.

Transaction ownership:

    This repository flushes changes but does not commit transactions.
    The application service/request boundary owns transaction commits
    and rollbacks.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.core.repositories import TenantScopedRepository
from app.core.tenant_scope import (
    tenant_scoped_delete,
    tenant_scoped_update,
)
from app.modules.customers.models import Customer, CustomerStatus


class CustomerRepository(TenantScopedRepository[Customer]):
    """
    Tenant-scoped repository for Customer records.

    The tenant_id supplied to this repository must come from the
    authenticated TenantContext/application service.

    All inherited operations are automatically tenant-scoped:

        get_by_id()
        list()
        count()
        add()

    Customer-specific operations in this repository also enforce
    the same tenant boundary.
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        """
        Initialize the customer repository.

        Args:
            db: Active SQLAlchemy async database session.
            tenant_id: Authorized tenant UUID obtained from the
                application tenant context.
        """
        super().__init__(
            db=db,
            model=Customer,
            tenant_id=tenant_id,
        )

    async def get_by_email(
        self,
        email: str,
    ) -> Customer | None:
        """
        Retrieve a customer by email within the current tenant.

        The same email may legitimately exist in another tenant.

        Therefore, the lookup always includes the repository tenant
        scope.
        """
        normalized_email = email.strip().lower()

        statement = self.scoped_select().where(
            func.lower(Customer.email) == normalized_email,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_phone(
        self,
        phone: str,
    ) -> Customer | None:
        """
        Retrieve a customer by phone number within the current tenant.

        Phone normalization is intentionally limited here to whitespace
        trimming. Full international phone normalization can be added
        later as a dedicated domain/value-object concern.
        """
        normalized_phone = phone.strip()

        statement = self.scoped_select().where(
            Customer.phone == normalized_phone,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        pagination: PaginationParams,
    ) -> list[Customer]:
        """
        Search customers belonging only to the current tenant.

        Search fields:

        - first name
        - last name
        - email
        - phone
        - company name

        PostgreSQL ILIKE is used for case-insensitive matching.

        SQL LIKE wildcard characters are escaped so user input does not
        unintentionally become an unrestricted wildcard expression.
        """
        normalized_query = query.strip()

        if not normalized_query:
            return []

        escaped_query = (
            normalized_query
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        pattern = f"%{escaped_query}%"

        statement = (
            self.scoped_select()
            .where(
                or_(
                    Customer.first_name.ilike(
                        pattern,
                        escape="\\",
                    ),
                    Customer.last_name.ilike(
                        pattern,
                        escape="\\",
                    ),
                    Customer.email.ilike(
                        pattern,
                        escape="\\",
                    ),
                    Customer.phone.ilike(
                        pattern,
                        escape="\\",
                    ),
                    Customer.company_name.ilike(
                        pattern,
                        escape="\\",
                    ),
                ),
            )
            .order_by(
                Customer.created_at.desc(),
                Customer.id,
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def list_filtered(
        self,
        pagination: PaginationParams,
        *,
        status: CustomerStatus | None = None,
    ) -> list[Customer]:
        """
        Retrieve tenant customers with optional status filtering.

        The tenant scope is always applied before the optional status
        filter.
        """
        statement = self.scoped_select()

        if status is not None:
            statement = statement.where(
                Customer.status == status,
            )

        statement = (
            statement
            .order_by(
                Customer.created_at.desc(),
                Customer.id,
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        status: CustomerStatus | None = None,
    ) -> int:
        """
        Count tenant customers with optional status filtering.

        This method never counts customers belonging to another tenant.
        """
        statement = select(
            func.count(),
        ).select_from(Customer).where(
            Customer.tenant_id == self.tenant_id,
        )

        if status is not None:
            statement = statement.where(
                Customer.status == status,
            )

        result = await self.db.execute(statement)

        return int(result.scalar_one())

    async def update(
        self,
        customer_id: UUID,
        values: dict[str, Any],
    ) -> Customer | None:
        """
        Update a customer belonging to the current tenant.

        The tenant_id field can never be changed through this method.

        The record is first retrieved through get_by_id(), which means
        a customer belonging to another tenant behaves as nonexistent.

        The method flushes but does not commit.
        """
        customer = await self.get_by_id(customer_id)

        if customer is None:
            return None

        # Never allow persistence-layer callers to change ownership.
        values = dict(values)
        values.pop("tenant_id", None)
        values.pop("id", None)

        for field_name, value in values.items():
            if not hasattr(Customer, field_name):
                raise ValueError(
                    f"Unknown customer field: {field_name}",
                )

            setattr(
                customer,
                field_name,
                value,
            )

        await self.db.flush()

        return customer

    async def delete(
        self,
        customer_id: UUID,
    ) -> bool:
        """
        Delete a customer belonging to the current tenant.

        The DELETE statement contains an explicit tenant predicate.

        Returns:
            True when a customer was deleted.
            False when the customer does not exist in this tenant.

        The method flushes but does not commit.
        """
        statement = tenant_scoped_delete(
            Customer,
            self.tenant_id,
        ).where(
            Customer.id == customer_id,
        )

        result = await self.db.execute(statement)

        await self.db.flush()

        return result.rowcount == 1

    async def update_direct(
        self,
        customer_id: UUID,
        values: dict[str, Any],
    ) -> bool:
        """
        Perform a tenant-scoped SQL UPDATE.

        This lower-level operation is useful when the application service
        does not need the updated ORM object immediately.

        The tenant_id field is explicitly removed from the update payload
        so ownership cannot be transferred between tenants.

        Returns:
            True when a record was updated.
            False when the customer does not exist in this tenant.

        The method flushes but does not commit.
        """
        values = dict(values)

        # Ownership must never be changed by a customer update.
        values.pop("tenant_id", None)
        values.pop("id", None)

        if not values:
            return False

        statement = (
            tenant_scoped_update(
                Customer,
                self.tenant_id,
            )
            .where(
                Customer.id == customer_id,
            )
            .values(**values)
        )

        result = await self.db.execute(statement)

        await self.db.flush()

        return result.rowcount == 1