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

from sqlalchemy import func, or_, select
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
        Retrieve a customer by phone within the current tenant.
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

    async def count_by_status(
        self,
        status: CustomerStatus,
    ) -> int:
        """
        Count customers with a specific status inside the current tenant.

        The tenant boundary is applied through scoped_select().
        """

        statement = (
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.tenant_id == self.tenant_id,
                Customer.status == status,
            )
        )

        result = await self.db.execute(statement)

        return int(result.scalar_one())

    async def search(
        self,
        query: str,
        pagination: PaginationParams,
    ) -> list[Customer]:
        """
        Search customers within the current tenant.

        Search fields:

        - first name
        - last name
        - email
        - phone
        - company name

        SQL LIKE wildcard characters supplied by the caller are escaped
        so they are treated as literal search text.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return await self.list(pagination)

        statement = self._search_statement(
            normalized_query,
            pagination,
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count_search(
        self,
        query: str,
    ) -> int:
        """
        Count search matches inside the current tenant.

        Empty search input delegates to the normal tenant-scoped count.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return await self.count()

        escaped_query = self._escape_search_query(
            normalized_query,
        )

        pattern = f"%{escaped_query}%"

        statement = (
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.tenant_id == self.tenant_id,
                self._search_predicate(pattern),
            )
        )

        result = await self.db.execute(statement)

        return int(result.scalar_one())

    def _search_statement(
        self,
        query: str,
        pagination: PaginationParams,
    ):
        """
        Build the tenant-scoped customer search statement.
        """

        escaped_query = self._escape_search_query(query)
        pattern = f"%{escaped_query}%"

        return (
            self.scoped_select()
            .where(
                self._search_predicate(pattern),
            )
            .order_by(
                Customer.created_at.desc(),
                Customer.id.desc(),
            )
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

    @staticmethod
    def _escape_search_query(
        query: str,
    ) -> str:
        """
        Escape SQL LIKE wildcard characters.
        """

        return (
            query
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    @staticmethod
    def _search_predicate(
        pattern: str,
    ):
        """
        Build the common customer search predicate.
        """

        return or_(
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
        )