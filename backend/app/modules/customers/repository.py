"""
Tenant-scoped customer repository.

The CustomerRepository provides customer-specific persistence operations
on top of the reusable TenantScopedRepository.

Security boundary:

    Every operation is automatically restricted to the repository tenant.

The repository does not authenticate users, authorize roles, or determine
tenant identity. Those responsibilities belong to the authentication,
authorization, and application-service layers.
"""

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.core.repositories import TenantScopedRepository
from app.modules.customers.models import Customer, CustomerStatus


class CustomerRepository(TenantScopedRepository[Customer]):
    """
    Persistence repository for tenant-owned customers.

    The repository is permanently bound to one tenant through the
    TenantScopedRepository constructor.

    All customer-specific queries therefore inherit the same tenant
    isolation guarantee as the generic repository.
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> None:
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

        An identical email belonging to another tenant is intentionally
        invisible to this repository.
        """
        statement = self.scoped_select().where(
            Customer.email == email,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_phone(
        self,
        phone: str,
    ) -> Customer | None:
        """
        Retrieve a customer by phone number within the current tenant.

        An identical phone number belonging to another tenant is
        intentionally invisible to this repository.
        """
        statement = self.scoped_select().where(
            Customer.phone == phone,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        status: CustomerStatus,
        pagination: PaginationParams,
    ) -> list[Customer]:
        """
        Retrieve customers with a specific lifecycle status.

        Tenant filtering is combined with the status predicate.
        """
        statement = (
            self.scoped_select()
            .where(
                Customer.status == status,
            )
            .order_by(
                Customer.created_at.desc(),
                Customer.id.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def search(
        self,
        query: str,
        pagination: PaginationParams,
    ) -> list[Customer]:
        """
        Search customers within the current tenant.

        The search covers:

        - first name
        - last name
        - email
        - phone
        - company name

        SQL LIKE wildcard characters supplied by the user are escaped so
        that search input is treated as search text rather than allowing
        callers to alter the intended wildcard pattern.
        """
        normalized_query = query.strip()

        if not normalized_query:
            return await self.list(pagination)

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
                Customer.id.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())