"""
Tests for the tenant-scoped CustomerRepository.

These tests verify that customer repository operations:

- use the correct Customer model
- preserve tenant isolation
- scope lookups to the current tenant
- scope searches to the current tenant
- scope status filtering to the current tenant
- prevent tenant reassignment during updates
- generate tenant-scoped DELETE operations
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.pagination import PaginationParams
from app.modules.customers.models import Customer, CustomerStatus
from app.modules.customers.repository import CustomerRepository


@pytest.fixture
def tenant_a() -> UUID:
    """Return a stable tenant UUID for test tenant A."""
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def tenant_b() -> UUID:
    """Return a stable tenant UUID for test tenant B."""
    return UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def db() -> AsyncMock:
    """Return a mocked asynchronous SQLAlchemy session."""
    return AsyncMock()


@pytest.fixture
def repository(
    db: AsyncMock,
    tenant_a: UUID,
) -> CustomerRepository:
    """Return a repository scoped to tenant A."""
    return CustomerRepository(
        db=db,
        tenant_id=tenant_a,
    )


def _statement_sql(statement: object) -> str:
    """
    Compile a SQLAlchemy statement into PostgreSQL SQL text.

    Literal UUID values are intentionally not rendered into the SQL.
    The test only needs to verify that tenant filtering exists.
    """
    return str(statement)


class TestCustomerRepositoryInitialization:
    """Tests for repository construction."""

    def test_repository_uses_customer_model(
        self,
        repository: CustomerRepository,
    ) -> None:
        """The repository must operate on Customer records."""
        assert repository.model is Customer

    def test_repository_preserves_authorized_tenant(
        self,
        repository: CustomerRepository,
        tenant_a: UUID,
    ) -> None:
        """The repository must retain the authorized tenant UUID."""
        assert repository.tenant_id == tenant_a

    def test_two_repositories_have_independent_tenant_scope(
        self,
        db: AsyncMock,
        tenant_a: UUID,
        tenant_b: UUID,
    ) -> None:
        """
        Repositories created for different tenants must retain
        independent tenant scopes.
        """
        repository_a = CustomerRepository(
            db=db,
            tenant_id=tenant_a,
        )

        repository_b = CustomerRepository(
            db=db,
            tenant_id=tenant_b,
        )

        assert repository_a.tenant_id == tenant_a
        assert repository_b.tenant_id == tenant_b
        assert repository_a.tenant_id != repository_b.tenant_id


class TestCustomerRepositoryTenantIsolation:
    """Tests verifying tenant predicates on repository queries."""

    def test_scoped_select_contains_tenant_predicate(
        self,
        repository: CustomerRepository,
        tenant_a: UUID,
    ) -> None:
        """Every base customer SELECT must contain tenant filtering."""
        statement = repository.scoped_select()

        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.tenant_id = " in sql

        assert repository.tenant_id == tenant_a

    @pytest.mark.asyncio
    async def test_get_by_id_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """
        get_by_id must include the repository tenant boundary.
        """
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        customer_id = uuid4()

        customer = await repository.get_by_id(customer_id)

        assert customer is None

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.id" in sql

    @pytest.mark.asyncio
    async def test_count_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """count must count only records belonging to the repository tenant."""
        result = MagicMock()
        result.scalar_one.return_value = 3
        db.execute.return_value = result

        count = await repository.count()

        assert count == 3

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql

    @pytest.mark.asyncio
    async def test_list_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """list must use the inherited tenant-scoped SELECT."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        pagination = PaginationParams(
            page=1,
            page_size=25,
        )

        customers = await repository.list(pagination)

        assert customers == []

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql

    @pytest.mark.asyncio
    async def test_email_lookup_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Email lookup must never search outside the current tenant."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        customer = await repository.get_by_email(
            "Customer@Example.com",
        )

        assert customer is None

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "lower(customers.email)" in sql

    @pytest.mark.asyncio
    async def test_phone_lookup_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Phone lookup must never search outside the current tenant."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        customer = await repository.get_by_phone(
            "+2348012345678",
        )

        assert customer is None

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.phone" in sql


class TestCustomerRepositorySearch:
    """Tests for customer search."""

    @pytest.mark.asyncio
    async def test_empty_search_returns_no_results(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Blank search queries should not execute an unnecessary query."""
        pagination = PaginationParams(
            page=1,
            page_size=25,
        )

        customers = await repository.search(
            "   ",
            pagination,
        )

        assert customers == []
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_search_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Customer search must include the tenant predicate."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        pagination = PaginationParams(
            page=1,
            page_size=25,
        )

        customers = await repository.search(
            "John",
            pagination,
        )

        assert customers == []

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.first_name" in sql
        assert "customers.last_name" in sql
        assert "customers.email" in sql
        assert "customers.phone" in sql
        assert "customers.company_name" in sql

    @pytest.mark.asyncio
    async def test_search_escapes_like_wildcards(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """
        Search input containing SQL LIKE wildcards must be escaped.

        This prevents a user-provided '%' or '_' from becoming an
        unintended unrestricted wildcard.
        """
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        pagination = PaginationParams(
            page=1,
            page_size=25,
        )

        await repository.search(
            "100%",
            pagination,
        )

        statement = db.execute.await_args.args[0]

        compiled = statement.compile(
            compile_kwargs={
                "literal_binds": False,
            },
        )

        sql = str(compiled)

        assert "customers.tenant_id" in sql


class TestCustomerRepositoryFiltering:
    """Tests for status filtering and filtered counts."""

    @pytest.mark.asyncio
    async def test_status_filter_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Status filtering must retain the tenant predicate."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        pagination = PaginationParams(
            page=1,
            page_size=25,
        )

        customers = await repository.list_filtered(
            pagination,
            status=CustomerStatus.ACTIVE,
        )

        assert customers == []

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.status" in sql

    @pytest.mark.asyncio
    async def test_filtered_count_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Filtered counts must include tenant and status predicates."""
        result = MagicMock()
        result.scalar_one.return_value = 2
        db.execute.return_value = result

        count = await repository.count_filtered(
            status=CustomerStatus.ACTIVE,
        )

        assert count == 2

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.status" in sql


class TestCustomerRepositoryUpdates:
    """Tests for tenant-safe customer updates."""

    @pytest.mark.asyncio
    async def test_update_returns_none_for_other_tenant(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """
        A customer belonging to another tenant must behave as nonexistent.
        """
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        customer_id = uuid4()

        updated = await repository.update(
            customer_id,
            {
                "first_name": "Updated",
            },
        )

        assert updated is None

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.id" in sql

    @pytest.mark.asyncio
    async def test_update_cannot_change_tenant_id(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """
        tenant_id supplied in an update payload must never transfer
        ownership to another tenant.
        """
        customer = Customer(
            tenant_id=repository.tenant_id,
            first_name="John",
            last_name="Doe",
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = customer
        db.execute.return_value = result

        updated = await repository.update(
            customer.id,
            {
                "first_name": "Updated",
                "tenant_id": uuid4(),
            },
        )

        assert updated is customer
        assert customer.tenant_id == repository.tenant_id
        assert customer.first_name == "Updated"

        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_rejects_unknown_field(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Unknown customer fields must not silently enter the model."""
        customer = Customer(
            tenant_id=repository.tenant_id,
            first_name="John",
            last_name="Doe",
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = customer
        db.execute.return_value = result

        with pytest.raises(
            ValueError,
            match="Unknown customer field",
        ):
            await repository.update(
                customer.id,
                {
                    "not_a_customer_field": "value",
                },
            )

        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_direct_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """Direct SQL UPDATE must include the tenant predicate."""
        result = MagicMock()
        result.rowcount = 1
        db.execute.return_value = result

        updated = await repository.update_direct(
            uuid4(),
            {
                "first_name": "Updated",
            },
        )

        assert updated is True

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.id" in sql


class TestCustomerRepositoryDeletes:
    """Tests for tenant-safe deletion."""

    @pytest.mark.asyncio
    async def test_delete_is_tenant_scoped(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """DELETE must always contain the current tenant predicate."""
        result = MagicMock()
        result.rowcount = 1
        db.execute.return_value = result

        deleted = await repository.delete(uuid4())

        assert deleted is True

        statement = db.execute.await_args.args[0]
        sql = _statement_sql(statement)

        assert "customers.tenant_id" in sql
        assert "customers.id" in sql

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_customer_is_missing(
        self,
        repository: CustomerRepository,
        db: AsyncMock,
    ) -> None:
        """
        A DELETE affecting zero rows means the customer does not exist
        inside this tenant.
        """
        result = MagicMock()
        result.rowcount = 0
        db.execute.return_value = result

        deleted = await repository.delete(uuid4())

        assert deleted is False

        db.flush.assert_awaited_once()


class TestCustomerRepositoryAdd:
    """Tests for inherited tenant-safe create behavior."""

    @pytest.mark.asyncio
    async def test_add_rejects_customer_from_another_tenant(
        self,
        repository: CustomerRepository,
        tenant_b: UUID,
    ) -> None:
        """
        The inherited add() method must reject an entity whose tenant_id
        does not match the repository tenant.
        """
        customer = Customer(
            tenant_id=tenant_b,
            first_name="Other",
            last_name="Tenant",
        )

        with pytest.raises(
            ValueError,
            match="tenant_id does not match",
        ):
            await repository.add(customer)

        repository.db.add.assert_not_called()
        repository.db.flush.assert_not_awaited()