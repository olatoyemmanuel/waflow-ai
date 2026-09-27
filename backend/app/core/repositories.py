"""
Reusable tenant-scoped repository primitives.

Repositories are responsible for persistence operations.

Security boundary:

    The repository receives an already-authorized tenant_id and applies
    that tenant scope to every tenant-owned database operation.

Repositories do not authenticate users and do not decide whether a user
is allowed to access a tenant. Those responsibilities belong to the
authentication and authorization layers.

Expected flow:

    TenantContext
        ↓
    Application Service
        ↓
    TenantScopedRepository
        ↓
    PostgreSQL
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.pagination import PaginationParams
from app.core.tenant_scope import tenant_scoped_select

ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    """
    Base repository for tenant-owned SQLAlchemy ORM models.

    The repository requires an authorized tenant_id when instantiated.

    Every tenant-owned read is automatically scoped to that tenant.

    Create operations additionally verify that:

    1. The entity is an instance of the repository model.
    2. The entity tenant_id matches the repository tenant_id.
    """

    def __init__(
        self,
        db: AsyncSession,
        model: type[ModelT],
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.model = model
        self.tenant_id = tenant_id

    def scoped_select(self) -> Select[Any]:
        """
        Return a SELECT statement already restricted to this tenant.
        """
        return tenant_scoped_select(
            self.model,
            self.tenant_id,
        )

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> ModelT | None:
        """
        Retrieve one tenant-owned record by primary key.

        A record belonging to another tenant behaves as missing because
        the tenant predicate is part of the SELECT statement.
        """
        statement = self.scoped_select().where(
            self.model.id == record_id,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list(
        self,
        pagination: PaginationParams,
    ) -> list[ModelT]:
        """
        Retrieve a paginated list of records belonging to this tenant.
        """
        statement = (
            self.scoped_select()
            .offset(pagination.offset)
            .limit(pagination.limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count(self) -> int:
        """
        Count records belonging to this tenant.
        """
        statement = select(
            func.count(),
        ).select_from(self.model).where(
            self.model.tenant_id == self.tenant_id,
        )

        result = await self.db.execute(statement)

        return int(result.scalar_one())

    async def add(
        self,
        entity: ModelT,
    ) -> ModelT:
        """
        Add a tenant-owned entity to the current session.

        Two invariants are enforced before persistence:

        1. The entity must be an instance of this repository's model.
        2. The entity's tenant_id must match the repository tenant.

        The method does not commit. Transaction ownership remains with
        the application service/request boundary.
        """
        if not isinstance(entity, self.model):
            raise TypeError(
                "Entity type does not match the repository model.",
            )

        entity_tenant_id = getattr(
            entity,
            "tenant_id",
            None,
        )

        if entity_tenant_id != self.tenant_id:
            raise ValueError(
                "Entity tenant_id does not match the repository tenant.",
            )

        self.db.add(entity)

        await self.db.flush()

        return entity
