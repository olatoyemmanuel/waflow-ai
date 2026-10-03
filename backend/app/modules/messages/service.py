"""
WAFlow AI message service.

This service contains application-level business logic for Message entities.

Security principles:

- Tenant identity always comes from TenantContext.
- A caller cannot choose or override the tenant_id of a message.
- Conversations are validated through the tenant-scoped ConversationRepository.
- Repository methods remain responsible for persistence queries.
- The service owns business validation and transaction coordination.
- Repository methods never commit transactions.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.services import TenantContext, TenantScopedService
from app.modules.conversations.repository import ConversationRepository
from app.modules.messages.models import (
    Message,
    MessageDirection,
    MessageSenderType,
    MessageStatus,
    MessageType,
)
from app.modules.messages.repository import MessageRepository


class MessageService(TenantScopedService[Message]):
    """
    Application service for tenant-scoped Message operations.

    A Message belongs to a Conversation. Therefore, message creation and
    conversation-scoped operations validate the conversation through the
    tenant-scoped ConversationRepository before accessing message data.
    """

    def __init__(
        self,
        repository: MessageRepository,
        conversation_repository: ConversationRepository,
        tenant_context: TenantContext,
    ) -> None:
        # The message repository must operate inside the same tenant
        # boundary as the authenticated tenant context.
        super().__init__(
            repository=repository,
            tenant_context=tenant_context,
        )

        # The conversation repository is another tenant-scoped dependency.
        # Keeping the validation here prevents a message from being attached
        # to a conversation belonging to another tenant.
        if conversation_repository.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                "Conversation repository tenant does not match "
                "the tenant context.",
            )

        self.conversation_repository = conversation_repository

    async def create(
        self,
        *,
        conversation_id: UUID,
        direction: MessageDirection,
        sender_type: MessageSenderType,
        message_type: MessageType = MessageType.TEXT,
        content: str | None = None,
        provider_message_id: str | None = None,
        status: MessageStatus = MessageStatus.PENDING,
        sender_user_id: UUID | None = None,
    ) -> Message:
        """
        Create a message inside the current tenant.

        The conversation must belong to the active tenant before the message
        is created.
        """
        conversation = await self.conversation_repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            raise ValueError(
                "Conversation does not exist in the current tenant.",
            )

        # Provider message IDs normally originate from WhatsApp or another
        # external messaging provider. Prevent duplicate provider IDs inside
        # the same tenant.
        if provider_message_id is not None:
            existing = (
                await self.repository.get_by_provider_message_id(
                    provider_message_id,
                )
            )

            if existing is not None:
                raise ValueError(
                    "A message with this provider_message_id already exists.",
                )

        # Message tenant ownership is derived exclusively from the
        # authenticated TenantContext.
        message = Message(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            sender_user_id=sender_user_id,
            direction=direction,
            sender_type=sender_type,
            message_type=message_type,
            status=status,
            content=content,
            provider_message_id=provider_message_id,
        )

        await self.repository.add(message)
        await self.repository.db.refresh(message)

        return message

    async def get(self, message_id: UUID) -> Message | None:
        """
        Retrieve a message by ID.

        TenantScopedRepository guarantees that the lookup remains restricted
        to the current tenant.
        """
        return await self.repository.get_by_id(message_id)

    async def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> Message | None:
        """
        Retrieve a message using an external provider message ID.

        The repository performs the tenant boundary enforcement.
        """
        return await self.repository.get_by_provider_message_id(
            provider_message_id,
        )

    async def list_by_conversation(
        self,
        conversation_id: UUID,
    ) -> list[Message]:
        """
        Return messages belonging to a tenant-owned conversation.

        The conversation is validated first so that callers cannot use
        conversation IDs as an indirect cross-tenant access mechanism.
        """
        conversation = await self.conversation_repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return []

        return await self.repository.list_by_conversation(
            conversation_id,
        )

    async def count_by_conversation(
        self,
        conversation_id: UUID,
    ) -> int:
        """
        Count messages belonging to a tenant-owned conversation.
        """
        conversation = await self.conversation_repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return 0

        return await self.repository.count_by_conversation(
            conversation_id,
        )

    async def list_by_direction(
        self,
        direction: MessageDirection,
    ) -> list[Message]:
        """Return messages filtered by inbound/outbound direction."""
        return await self.repository.list_by_direction(direction)

    async def count_by_direction(
        self,
        direction: MessageDirection,
    ) -> int:
        """Count messages filtered by inbound/outbound direction."""
        return await self.repository.count_by_direction(direction)

    async def list_by_sender_type(
        self,
        sender_type: MessageSenderType,
    ) -> list[Message]:
        """Return messages filtered by sender classification."""
        return await self.repository.list_by_sender_type(sender_type)

    async def count_by_sender_type(
        self,
        sender_type: MessageSenderType,
    ) -> int:
        """Count messages filtered by sender classification."""
        return await self.repository.count_by_sender_type(sender_type)

    async def list_by_message_type(
        self,
        message_type: MessageType,
    ) -> list[Message]:
        """Return messages filtered by message type."""
        return await self.repository.list_by_message_type(message_type)

    async def count_by_message_type(
        self,
        message_type: MessageType,
    ) -> int:
        """Count messages filtered by message type."""
        return await self.repository.count_by_message_type(message_type)

    async def list_by_status(
        self,
        status: MessageStatus,
    ) -> list[Message]:
        """Return messages filtered by delivery status."""
        return await self.repository.list_by_status(status)

    async def count_by_status(
        self,
        status: MessageStatus,
    ) -> int:
        """Count messages filtered by delivery status."""
        return await self.repository.count_by_status(status)

    async def change_status(
        self,
        message_id: UUID,
        status: MessageStatus,
    ) -> Message:
        """
        Change the delivery status of a message.

        The message must belong to the current tenant.
        """
        message = await self.repository.get_by_id(message_id)

        if message is None:
            raise ValueError(
                "Message does not exist in the current tenant.",
            )

        message.status = status

        await self.repository.db.flush()
        await self.repository.db.refresh(message)

        return message

    async def update_content(
        self,
        message_id: UUID,
        content: str | None,
    ) -> Message:
        """
        Update message content.

        This operation is intentionally explicit rather than exposing a
        generic update dictionary. This keeps message mutation predictable.
        """
        message = await self.repository.get_by_id(message_id)

        if message is None:
            raise ValueError(
                "Message does not exist in the current tenant.",
            )

        message.content = content

        await self.repository.db.flush()
        await self.repository.db.refresh(message)

        return message

    async def update_provider_message_id(
        self,
        message_id: UUID,
        provider_message_id: str | None,
    ) -> Message:
        """
        Set or replace the external provider message identifier.

        When a provider ID is supplied, the service checks for an existing
        message with the same identifier inside the current tenant.
        """
        message = await self.repository.get_by_id(message_id)

        if message is None:
            raise ValueError(
                "Message does not exist in the current tenant.",
            )

        if provider_message_id is not None:
            existing = (
                await self.repository.get_by_provider_message_id(
                    provider_message_id,
                )
            )

            # Ignore the current message when checking for duplicates.
            if existing is not None and existing.id != message.id:
                raise ValueError(
                    "A message with this provider_message_id already exists.",
                )

        message.provider_message_id = provider_message_id

        await self.repository.db.flush()
        await self.repository.db.refresh(message)

        return message

    async def update_last_message_timestamp(
        self,
        message_id: UUID,
        timestamp: datetime,
    ) -> Message:
        """
        Update the message creation timestamp.

        This method exists for controlled application workflows that need to
        reconcile externally supplied message timestamps.
        """
        message = await self.repository.get_by_id(message_id)

        if message is None:
            raise ValueError(
                "Message does not exist in the current tenant.",
            )

        message.created_at = timestamp

        await self.repository.db.flush()
        await self.repository.db.refresh(message)

        return message