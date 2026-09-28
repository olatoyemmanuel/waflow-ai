"""
Customer application service.

The CustomerService coordinates customer-related use cases between the
API layer and the tenant-scoped CustomerRepository.

Responsibilities:

- enforce application-level customer rules
- derive tenant ownership from TenantContext
- prevent cross-tenant repository usage
- coordinate customer creation and updates
- handle duplicate contact information
- provide tenant-scoped reads
- archive customers instead of physically deleting them

The service does not authenticate users or implement HTTP concerns.
"""

from __future__ import annotations

from uuid import UUID

from app.core.pagination import (
    PaginationMeta,
    PaginationParams,
    build_pagination_meta,
)
from app.core.services import TenantScopedService
from app.modules.auth.dependencies import TenantContext
from app.modules.customers.models import Customer, CustomerStatus
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate


class CustomerService(TenantScopedService[Customer]):
    """
    Application service for tenant-owned customers.

    The repository and TenantContext must belong to the same tenant.
    TenantScopedService verifies this invariant during construction.
    """

    def __init__(
        self,
        repository: CustomerRepository,
        tenant_context: TenantContext,
    ) -> None:
        super().__init__(
            repository=repository,
            tenant_context=tenant_context,
        )

    async def create(
        self,
        data: CustomerCreate,
    ) -> Customer:
        """
        Create a customer inside the authorized tenant.
        """

        if data.email is not None:
            existing_customer = await self.repository.get_by_email(
                data.email,
            )

            if existing_customer is not None:
                raise ValueError(
                    "A customer with this email already exists.",
                )

        if data.phone is not None:
            existing_customer = await self.repository.get_by_phone(
                data.phone,
            )

            if existing_customer is not None:
                raise ValueError(
                    "A customer with this phone number already exists.",
                )

        customer = Customer(
            tenant_id=self.tenant_id,
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            email=data.email,
            company_name=data.company_name,
            status=data.status,
            source=data.source,
            notes=data.notes,
        )

        return await self.repository.add(
            customer,
        )

    async def get(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        """
        Retrieve one customer inside the authorized tenant.
        """

        return await self.repository.get_by_id(
            customer_id,
        )

    async def list(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[Customer], PaginationMeta]:
        """
        Retrieve all customers using accurate tenant-scoped pagination.
        """

        return await super().list(
            pagination,
        )

    async def list_by_status(
        self,
        status: CustomerStatus,
        pagination: PaginationParams,
    ) -> tuple[list[Customer], PaginationMeta]:
        """
        Retrieve customers by status with an accurate total count.
        """

        records = await self.repository.list_by_status(
            status=status,
            pagination=pagination,
        )

        total = await self.repository.count_by_status(
            status,
        )

        metadata = build_pagination_meta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
        )

        return records, metadata

    async def search(
        self,
        query: str,
        pagination: PaginationParams,
    ) -> tuple[list[Customer], PaginationMeta]:
        """
        Search customers with an accurate tenant-scoped total.
        """

        records = await self.repository.search(
            query=query,
            pagination=pagination,
        )

        total = await self.repository.count_search(
            query,
        )

        metadata = build_pagination_meta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
        )

        return records, metadata

    async def update(
        self,
        customer_id: UUID,
        data: CustomerUpdate,
    ) -> Customer | None:
        """
        Update a customer belonging to the authorized tenant.

        Archiving is intentionally excluded from normal updates. The
        dedicated archive use case requires the customers.delete
        permission at the API authorization layer.
        """

        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        update_values = data.model_dump(
            exclude_unset=True,
        )

        # SECURITY BOUNDARY:
        #
        # Do not allow a caller with customers.update permission to archive
        # a customer through PATCH. Archiving must use the dedicated
        # operation protected by customers.delete.
        if update_values.get("status") == CustomerStatus.ARCHIVED:
            raise ValueError(
                "Archiving a customer requires the archive operation.",
            )

        if "email" in update_values:
            email = update_values["email"]

            if email is not None:
                existing_customer = await self.repository.get_by_email(
                    email,
                )

                if (
                    existing_customer is not None
                    and existing_customer.id != customer.id
                ):
                    raise ValueError(
                        "A customer with this email already exists.",
                    )

        if "phone" in update_values:
            phone = update_values["phone"]

            if phone is not None:
                existing_customer = await self.repository.get_by_phone(
                    phone,
                )

                if (
                    existing_customer is not None
                    and existing_customer.id != customer.id
                ):
                    raise ValueError(
                        "A customer with this phone number already exists.",
                    )

        for field_name, value in update_values.items():
            setattr(
                customer,
                field_name,
                value,
            )

        # Flush the UPDATE first so the database applies the server-side
        # updated_at=now() value.
        await self.repository.db.flush()

        # Explicitly reload server-generated fields before returning the
        # ORM object. This prevents Pydantic serialization from triggering
        # implicit asynchronous I/O and causing MissingGreenlet.
        await self.repository.db.refresh(
            customer,
        )

        return customer

    async def archive(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        """
        Archive a customer without physically deleting its database row.

        API authorization requires customers.delete for this operation.
        """

        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        customer.status = CustomerStatus.ARCHIVED

        # Persist the mutation.
        await self.repository.db.flush()

        # Reload server-generated updated_at before the ORM object crosses
        # the async application boundary.
        await self.repository.db.refresh(
            customer,
        )

        return customer

    async def restore(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        """
        Restore an archived customer to ACTIVE status.

        API authorization requires customers.update for this operation.
        """

        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        customer.status = CustomerStatus.ACTIVE

        # Persist the mutation.
        await self.repository.db.flush()

        # Reload server-generated updated_at before response serialization.
        await self.repository.db.refresh(
            customer,
        )

        return customer