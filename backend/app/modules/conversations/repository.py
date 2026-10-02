"""
WAFlow AI conversation repository.

This repository contains tenant-scoped persistence queries specific to
Conversation entities.

Security principles:

- Every query is automatically restricted to the active tenant.
- The repository never trusts a tenant_id supplied by a caller.
- Tenant ownership comes exclusively from the repository tenant boundary.
- Persistence logic stays out of services and API routes.
- The repository does not commit transactions; transaction ownership
  remains with the application/service layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import TenantScopedRepository
from app.modules.conversations.models import (
    Conversation,
    ConversationChannel,
    ConversationHandlingMode,
    ConversationStatus,
)


class ConversationRepository(TenantScopedRepository[Conversation]):
    """
    Tenant-scoped repository for Conversation persistence.

    The base TenantScopedRepository guarantees that all entity queries
    are restricted to the tenant supplied when this repository is created.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        # TenantScopedRepository's established constructor contract is:
        #
        #     TenantScopedRepository(session, model, tenant_id)
        #
        # The base repository stores the supplied AsyncSession as `db`.
        super().__init__(
            session,
            Conversation,
            tenant_id,
        )

    def _base_query(self) -> Select[tuple[Conversation]]:
        """
        Build the base tenant-scoped Conversation query.

        Tenant filtering is delegated to TenantScopedRepository so that
        specialized repository methods cannot accidentally omit it.
        """
        return self.scoped_select()

    async def get_by_customer(
        self,
        customer_id: uuid.UUID,
    ) -> list[Conversation]:
        """
        Return all conversations belonging to one customer.

        Results are ordered with the most recently active conversation
        first, followed by creation time and UUID for deterministic output.
        """
        statement = (
            self._base_query()
            .where(Conversation.customer_id == customer_id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_customer(
        self,
        customer_id: uuid.UUID,
    ) -> int:
        """Count conversations belonging to one customer."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.customer_id == customer_id,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_status(
        self,
        status: ConversationStatus,
    ) -> list[Conversation]:
        """Return tenant conversations filtered by lifecycle status."""
        statement = (
            self._base_query()
            .where(Conversation.status == status)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_status(
        self,
        status: ConversationStatus,
    ) -> int:
        """Count tenant conversations filtered by lifecycle status."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.status == status,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_channel(
        self,
        channel: ConversationChannel,
    ) -> list[Conversation]:
        """Return tenant conversations filtered by communication channel."""
        statement = (
            self._base_query()
            .where(Conversation.channel == channel)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_channel(
        self,
        channel: ConversationChannel,
    ) -> int:
        """Count tenant conversations filtered by communication channel."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.channel == channel,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_handling_mode(
        self,
        handling_mode: ConversationHandlingMode,
    ) -> list[Conversation]:
        """Return tenant conversations filtered by AI or human handling."""
        statement = (
            self._base_query()
            .where(Conversation.handling_mode == handling_mode)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_handling_mode(
        self,
        handling_mode: ConversationHandlingMode,
    ) -> int:
        """Count tenant conversations filtered by handling mode."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.handling_mode == handling_mode,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_assigned_user(
        self,
        assigned_user_id: uuid.UUID,
    ) -> list[Conversation]:
        """Return conversations assigned to a specific user."""
        statement = (
            self._base_query()
            .where(Conversation.assigned_user_id == assigned_user_id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
                Conversation.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_assigned_user(
        self,
        assigned_user_id: uuid.UUID,
    ) -> int:
        """Count conversations assigned to a specific user."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.assigned_user_id == assigned_user_id,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())