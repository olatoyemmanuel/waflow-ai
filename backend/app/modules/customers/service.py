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
        Create a new customer inside the authorized tenant.

        The tenant_id is never accepted from CustomerCreate. It is derived
        exclusively from TenantContext through this service.

        Raises:
            ValueError:
                When the email or phone already belongs to a customer
                inside the current tenant.
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
        Retrieve one customer belonging to the authorized tenant.

        Customers belonging to another tenant behave as nonexistent
        because the repository applies the tenant boundary.
        """
        return await self.repository.get_by_id(
            customer_id,
        )

    async def list(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[Customer], PaginationMeta]:
        """
        Retrieve paginated customers for the authorized tenant.

        The inherited TenantScopedService handles the tenant-scoped
        repository query and total count.
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
        Retrieve customers with a specific status.

        The current repository contract provides status-filtered records
        but does not yet expose a status-filtered count operation.

        Therefore, pagination metadata for this method currently reflects
        the number of records returned by the current page.

        A filtered count can be introduced later when the API contract
        requires accurate total counts for status-filtered collections.
        """
        records = await self.repository.list_by_status(
            status=status,
            pagination=pagination,
        )

        total = len(records)

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
        Search customers inside the authorized tenant.

        The repository performs the tenant-scoped search.

        The current repository contract does not yet expose a matching
        search-count operation, so the pagination metadata currently
        reflects the number of records returned by the current page.
        """
        records = await self.repository.search(
            query=query,
            pagination=pagination,
        )

        total = len(records)

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

        Ownership fields such as tenant_id and id are not present in the
        CustomerUpdate schema and therefore cannot be reassigned through
        this service.

        Duplicate email and phone values are checked against other
        customers within the same tenant.
        """
        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        update_values = data.model_dump(
            exclude_unset=True,
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

        await self.repository.db.flush()

        return customer

    async def archive(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        """
        Archive a customer without physically deleting the database row.

        Archived customers remain available for historical records and
        auditing while being excluded from normal active-customer flows
        at the application layer.
        """
        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        customer.status = CustomerStatus.ARCHIVED

        await self.repository.db.flush()

        return customer

    async def restore(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        """
        Restore an archived customer to ACTIVE status.
        """
        customer = await self.repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return None

        customer.status = CustomerStatus.ACTIVE

        await self.repository.db.flush()

        return customer