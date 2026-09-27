"""
Reusable application service primitives.

Application services coordinate use cases.

They sit between FastAPI routes and repositories:

    API Route
        ↓
    Authorization
        ↓
    TenantContext
        ↓
    Application Service
        ↓
    Repository

Application services must never determine tenant identity from
frontend input.

TenantContext is the authoritative source of tenant scope.

The repository must also be bound to exactly the same tenant. This
prevents accidental cross-tenant repository injection.
"""

from typing import Generic, TypeVar
from uuid import UUID

from app.core.pagination import (
    PaginationMeta,
    PaginationParams,
    build_pagination_meta,
)
from app.core.repositories import TenantScopedRepository
from app.modules.auth.dependencies import TenantContext

ModelT = TypeVar("ModelT")


class TenantScopedService(Generic[ModelT]):
    """
    Base application service for tenant-owned resources.

    The service receives:

    - an authorized TenantContext
    - a repository bound to that tenant

    The constructor verifies that both tenant boundaries agree.
    """

    def __init__(
        self,
        repository: TenantScopedRepository[ModelT],
        tenant_context: TenantContext,
    ) -> None:
        if repository.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                "Repository tenant does not match the tenant context.",
            )

        self.repository = repository
        self.tenant_context = tenant_context

    @property
    def tenant_id(self) -> UUID:
        """
        Return the authorized tenant ID from TenantContext.
        """
        return self.tenant_context.tenant_id

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> ModelT | None:
        """
        Retrieve a tenant-owned record through the repository.
        """
        return await self.repository.get_by_id(
            record_id,
        )

    async def list(
        self,
        pagination: PaginationParams,
    ) -> tuple[list[ModelT], PaginationMeta]:
        """
        Retrieve tenant-owned records and pagination metadata.
        """
        records = await self.repository.list(
            pagination,
        )

        total = await self.repository.count()

        metadata = build_pagination_meta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
        )

        return records, metadata
