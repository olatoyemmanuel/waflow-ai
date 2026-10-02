"""
WAFlow AI message repository.

This repository contains tenant-scoped persistence queries specific to
Message entities.

Security principles:

- Every query is automatically restricted to the active tenant.
- The repository never trusts a tenant_id supplied by a caller.
- Tenant ownership comes exclusively from the repository tenant boundary.
- Persistence logic stays out of services and API routes.
- The repository does not commit transactions; transaction ownership
  remains with the application/service layer.
- Provider message identifiers are always resolved inside the tenant
  boundary to prevent cross-tenant message access.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import TenantScopedRepository
from app.modules.messages.models import (
    Message,
    MessageDirection,
    MessageSenderType,
    MessageStatus,
    MessageType,
)


class MessageRepository(TenantScopedRepository[Message]):
    """
    Tenant-scoped repository for Message persistence.

    The base TenantScopedRepository guarantees that entity queries are
    restricted to the tenant supplied when this repository is created.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        # Established TenantScopedRepository constructor contract:
        #
        #     TenantScopedRepository(session, model, tenant_id)
        #
        # The base repository stores the AsyncSession as `db`.
        super().__init__(
            session,
            Message,
            tenant_id,
        )

    def _base_query(self) -> Select[tuple[Message]]:
        """
        Build the base tenant-scoped Message query.

        Tenant filtering is delegated to TenantScopedRepository so that
        specialized repository methods cannot accidentally omit it.
        """
        return self.scoped_select()

    async def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> Message | None:
        """
        Find a message using its external provider message identifier.

        The lookup remains tenant-scoped. This is important because
        provider identifiers must never become a cross-tenant lookup key.
        """
        statement = (
            self._base_query()
            .where(
                Message.provider_message_id == provider_message_id,
            )
            .limit(1)
        )

        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> list[Message]:
        """
        Return all messages belonging to a conversation.

        Messages are ordered chronologically, with UUID used as a
        deterministic tie-breaker.
        """
        statement = (
            self._base_query()
            .where(
                Message.conversation_id == conversation_id,
            )
            .order_by(
                Message.created_at.asc(),
                Message.id.asc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> int:
        """Count messages belonging to a conversation."""
        statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.conversation_id == conversation_id,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_direction(
        self,
        direction: MessageDirection,
    ) -> list[Message]:
        """Return tenant messages filtered by inbound/outbound direction."""
        statement = (
            self._base_query()
            .where(
                Message.direction == direction,
            )
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_direction(
        self,
        direction: MessageDirection,
    ) -> int:
        """Count tenant messages filtered by direction."""
        statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.direction == direction,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_sender_type(
        self,
        sender_type: MessageSenderType,
    ) -> list[Message]:
        """Return tenant messages filtered by sender classification."""
        statement = (
            self._base_query()
            .where(
                Message.sender_type == sender_type,
            )
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_sender_type(
        self,
        sender_type: MessageSenderType,
    ) -> int:
        """Count tenant messages filtered by sender classification."""
        statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.sender_type == sender_type,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_message_type(
        self,
        message_type: MessageType,
    ) -> list[Message]:
        """Return tenant messages filtered by message type."""
        statement = (
            self._base_query()
            .where(
                Message.message_type == message_type,
            )
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_message_type(
        self,
        message_type: MessageType,
    ) -> int:
        """Count tenant messages filtered by message type."""
        statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.message_type == message_type,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())

    async def list_by_status(
        self,
        status: MessageStatus,
    ) -> list[Message]:
        """Return tenant messages filtered by delivery status."""
        statement = (
            self._base_query()
            .where(
                Message.status == status,
            )
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def count_by_status(
        self,
        status: MessageStatus,
    ) -> int:
        """Count tenant messages filtered by delivery status."""
        statement = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.status == status,
            )
        )

        result = await self.db.execute(statement)
        return int(result.scalar_one())