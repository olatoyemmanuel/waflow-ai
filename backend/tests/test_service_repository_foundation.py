"""
Tests for the Milestone 4D service and repository foundation.

These tests verify:

- Repository tenant binding.
- Repository tenant-safe lookup behavior.
- Repository tenant-safe count behavior.
- Repository tenant validation during create operations.
- Repository model-type validation during create operations.
- Application service tenant context propagation.
- Application service pagination delegation.
- Application service repository/tenant consistency.

A real SQLAlchemy ORM model is used for repository query tests. This
ensures the tests exercise SQLAlchemy's actual ORM compilation rather
than relying on an artificial model that SQLAlchemy cannot compile.

The test model uses SQLAlchemy's UUID-compatible Uuid type so that the
test tenant_id has the same UUID semantics as the production tenant
context and repository.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.pagination import PaginationParams
from app.core.repositories import TenantScopedRepository
from app.core.services import TenantScopedService
from app.modules.auth.dependencies import TenantContext


class RepositoryTestBase(DeclarativeBase):
    """Base class for test-only SQLAlchemy models."""


class RepositoryTestCustomer(RepositoryTestBase):
    """
    Minimal tenant-owned ORM model used only by these tests.

    No database table is created during the tests. SQLAlchemy only needs
    the mapped model metadata to compile the repository statements.

    UUID fields intentionally match the UUID semantics used by the
    production tenant context and repository.
    """

    __tablename__ = "test_customers"

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )


class FakeResult:
    """Minimal async SQLAlchemy result substitute for unit tests."""

    def __init__(
        self,
        records: list[object],
    ) -> None:
        self.records = records

    def scalar_one_or_none(self) -> object | None:
        """Return the first record or None."""
        if not self.records:
            return None

        return self.records[0]

    def scalars(self) -> "FakeResult":
        """Return this object for chained SQLAlchemy-style calls."""
        return self

    def all(self) -> list[object]:
        """Return all configured records."""
        return self.records

    def scalar_one(self) -> int:
        """Return the number of configured records."""
        return len(self.records)


class FakeAsyncSession:
    """
    Minimal AsyncSession substitute for repository unit tests.

    The fake session captures executed statements and added entities so
    the tests can verify repository behavior without requiring a real
    database connection.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.executed_statements: list[object] = []
        self.result = FakeResult([])

    def add(
        self,
        entity: object,
    ) -> None:
        """Capture an entity added to the session."""
        self.added.append(entity)

    async def flush(self) -> None:
        """Simulate SQLAlchemy session flush."""
        return

    async def execute(
        self,
        statement: object,
    ) -> FakeResult:
        """Capture the statement and return the configured result."""
        self.executed_statements.append(statement)

        return self.result


def build_tenant_context(
    tenant_id: UUID | None = None,
) -> TenantContext:
    """
    Build a valid TenantContext for unit tests.

    A supplied tenant_id is used when the test needs to verify a
    specific tenant boundary.
    """
    return TenantContext(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        membership_id=uuid4(),
        role_id=uuid4(),
        role_name="OWNER",
    )


def build_repository(
    tenant_id: UUID,
    session: FakeAsyncSession,
) -> TenantScopedRepository[RepositoryTestCustomer]:
    """
    Build a repository bound to a specific authorized tenant.
    """
    return TenantScopedRepository(
        session,
        RepositoryTestCustomer,
        tenant_id,
    )


def test_repository_is_bound_to_authorized_tenant():
    """
    Repository tenant scope must come from the supplied tenant ID.
    """
    tenant_id = uuid4()
    session = FakeAsyncSession()

    repository = build_repository(
        tenant_id,
        session,
    )

    assert repository.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_repository_get_by_id_executes_tenant_scoped_query():
    """
    Repository lookups must execute through the tenant-scoped SELECT
    foundation.
    """
    tenant_id = uuid4()
    record_id = uuid4()

    session = FakeAsyncSession()

    expected_record = SimpleNamespace(
        id=record_id,
        tenant_id=tenant_id,
    )

    session.result = FakeResult(
        [expected_record],
    )

    repository = build_repository(
        tenant_id,
        session,
    )

    result = await repository.get_by_id(
        record_id,
    )

    assert result is expected_record
    assert len(session.executed_statements) == 1

    sql = str(
        session.executed_statements[0],
    )

    assert "test_customers" in sql
    assert "tenant_id" in sql


@pytest.mark.asyncio
async def test_repository_returns_none_when_record_is_not_found():
    """
    A missing tenant-scoped record must return None.
    """
    session = FakeAsyncSession()

    repository = build_repository(
        uuid4(),
        session,
    )

    result = await repository.get_by_id(
        uuid4(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_repository_count_is_tenant_scoped():
    """
    Count queries must contain the tenant boundary.
    """
    tenant_id = uuid4()
    session = FakeAsyncSession()

    session.result = FakeResult(
        [
            object(),
            object(),
            object(),
        ],
    )

    repository = build_repository(
        tenant_id,
        session,
    )

    count = await repository.count()

    assert count == 3
    assert len(session.executed_statements) == 1

    sql = str(
        session.executed_statements[0],
    )

    assert "test_customers" in sql
    assert "tenant_id" in sql


@pytest.mark.asyncio
async def test_repository_rejects_entity_from_different_tenant():
    """
    Repository create operations must reject an entity whose tenant_id
    does not match the repository's authorized tenant.

    The entity is intentionally created as the correct model type so
    this test specifically exercises tenant mismatch validation.
    """
    tenant_id = uuid4()
    different_tenant_id = uuid4()

    session = FakeAsyncSession()

    repository = build_repository(
        tenant_id,
        session,
    )

    entity = RepositoryTestCustomer(
        id=uuid4(),
        tenant_id=different_tenant_id,
        name="Wrong Tenant Customer",
    )

    with pytest.raises(
        ValueError,
        match="Entity tenant_id does not match",
    ):
        await repository.add(entity)

    assert session.added == []


@pytest.mark.asyncio
async def test_repository_rejects_entity_with_wrong_model_type():
    """
    Repository create operations must reject an entity that is not an
    instance of the repository's configured model.

    This prevents an unrelated object with a matching tenant_id from
    being accidentally persisted through the repository.
    """
    tenant_id = uuid4()

    session = FakeAsyncSession()

    repository = build_repository(
        tenant_id,
        session,
    )

    entity = SimpleNamespace(
        tenant_id=tenant_id,
    )

    with pytest.raises(
        TypeError,
        match="Entity type does not match the repository model",
    ):
        await repository.add(entity)

    assert session.added == []


@pytest.mark.asyncio
async def test_repository_accepts_entity_from_authorized_tenant():
    """
    Repository create operations should accept an entity belonging to
    the repository's tenant and configured model.
    """
    tenant_id = uuid4()

    session = FakeAsyncSession()

    repository = build_repository(
        tenant_id,
        session,
    )

    entity = RepositoryTestCustomer(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Authorized Tenant Customer",
    )

    result = await repository.add(entity)

    assert result is entity
    assert session.added == [entity]


@pytest.mark.asyncio
async def test_service_exposes_tenant_context_tenant_id():
    """
    Application services must expose the tenant established by
    TenantContext rather than accepting an independent tenant ID.
    """
    tenant_id = uuid4()

    context = build_tenant_context(
        tenant_id,
    )

    repository = build_repository(
        tenant_id,
        FakeAsyncSession(),
    )

    service = TenantScopedService(
        repository,
        context,
    )

    assert service.tenant_id == tenant_id
    assert service.tenant_id == context.tenant_id


@pytest.mark.asyncio
async def test_service_rejects_repository_from_different_tenant():
    """
    An application service must reject a repository that is bound to a
    different tenant than its authorized TenantContext.

    This prevents accidental cross-tenant repository injection.
    """
    context_tenant_id = uuid4()
    repository_tenant_id = uuid4()

    session = FakeAsyncSession()

    repository = build_repository(
        repository_tenant_id,
        session,
    )

    context = build_tenant_context(
        context_tenant_id,
    )

    with pytest.raises(
        ValueError,
        match="Repository tenant does not match the tenant context",
    ):
        TenantScopedService(
            repository,
            context,
        )


@pytest.mark.asyncio
async def test_service_get_by_id_delegates_to_repository():
    """
    The service should delegate persistence lookup to the repository.
    """
    tenant_id = uuid4()
    record_id = uuid4()

    session = FakeAsyncSession()

    expected_record = SimpleNamespace(
        id=record_id,
        tenant_id=tenant_id,
    )

    session.result = FakeResult(
        [expected_record],
    )

    repository = build_repository(
        tenant_id,
        session,
    )

    service = TenantScopedService(
        repository,
        build_tenant_context(tenant_id),
    )

    result = await service.get_by_id(
        record_id,
    )

    assert result is expected_record


@pytest.mark.asyncio
async def test_service_list_returns_records_and_pagination():
    """
    The service should combine repository records with pagination
    metadata.
    """
    tenant_id = uuid4()

    session = FakeAsyncSession()

    records = [
        SimpleNamespace(
            tenant_id=tenant_id,
        ),
        SimpleNamespace(
            tenant_id=tenant_id,
        ),
    ]

    session.result = FakeResult(records)

    repository = build_repository(
        tenant_id,
        session,
    )

    service = TenantScopedService(
        repository,
        build_tenant_context(tenant_id),
    )

    result_records, metadata = await service.list(
        PaginationParams(
            page=1,
            page_size=20,
        ),
    )

    assert result_records == records
    assert metadata.page == 1
    assert metadata.page_size == 20
    assert metadata.total == 2
    assert metadata.total_pages == 1
    assert metadata.has_next is False
    assert metadata.has_previous is False
