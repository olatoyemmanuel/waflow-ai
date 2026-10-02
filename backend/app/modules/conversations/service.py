"""
WAFlow AI conversation application service.

The ConversationService coordinates conversation-related use cases
between the API layer and the tenant-scoped repositories.

Responsibilities:

- enforce conversation application rules
- derive tenant ownership from TenantContext
- prevent cross-tenant repository usage
- validate that the referenced customer belongs to the active tenant
- coordinate conversation creation and lifecycle mutations
- provide tenant-scoped conversation reads
- manage assignment, handling mode, unread state, and timestamps

Security principles:

- Tenant identity comes exclusively from TenantContext.
- The service never accepts tenant_id as an application input.
- The ConversationRepository must belong to the same tenant as
  TenantContext.
- The CustomerRepository must belong to the same tenant as
  TenantContext.
- A conversation cannot be created for a customer belonging to
  another tenant.
- HTTP authorization and RBAC remain outside this service.

Important limitation:

The current identity module contains User and Membership models but does
not yet expose a MembershipRepository or membership service. Therefore,
this service does not independently validate that assigned_user_id belongs
to an active membership. That validation should be introduced as part of
the identity/assignment capability rather than inventing a second
authorization path here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.services import TenantScopedService
from app.modules.auth.dependencies import TenantContext
from app.modules.conversations.models import (
    Conversation,
    ConversationChannel,
    ConversationHandlingMode,
    ConversationStatus,
)
from app.modules.conversations.repository import ConversationRepository
from app.modules.customers.repository import CustomerRepository


class ConversationService(TenantScopedService[Conversation]):
    """
    Application service for tenant-owned conversations.

    Both repositories must belong to the same tenant as TenantContext.
    TenantScopedService verifies the conversation repository boundary,
    while this service verifies the customer repository boundary.
    """

    def __init__(
        self,
        repository: ConversationRepository,
        customer_repository: CustomerRepository,
        tenant_context: TenantContext,
    ) -> None:
        # TenantScopedService verifies that the conversation repository
        # belongs to the authorized tenant context.
        super().__init__(
            repository=repository,
            tenant_context=tenant_context,
        )

        # The customer repository participates in customer ownership
        # validation during conversation creation. It must therefore
        # be bound to exactly the same tenant.
        if customer_repository.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                "Customer repository tenant does not match the tenant context.",
            )

        self.customer_repository = customer_repository

    async def create(
        self,
        customer_id: UUID,
        *,
        channel: ConversationChannel = ConversationChannel.WHATSAPP,
        status: ConversationStatus = ConversationStatus.OPEN,
        handling_mode: ConversationHandlingMode = ConversationHandlingMode.AI,
    ) -> Conversation:
        """
        Create a conversation for a customer inside the authorized tenant.

        The customer is resolved through the tenant-scoped
        CustomerRepository. A customer belonging to another tenant behaves
        as missing and therefore cannot be used to create the conversation.

        Tenant ownership is always derived from TenantContext.
        """

        customer = await self.customer_repository.get_by_id(
            customer_id,
        )

        if customer is None:
            raise ValueError(
                "Customer does not exist in the authorized tenant.",
            )

        conversation = Conversation(
            tenant_id=self.tenant_id,
            customer_id=customer.id,
            channel=channel,
            status=status,
            handling_mode=handling_mode,
            unread_count=0,
        )

        return await self.repository.add(
            conversation,
        )

    async def get(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        """
        Retrieve one conversation inside the authorized tenant.
        """

        return await self.repository.get_by_id(
            conversation_id,
        )

    async def list_by_customer(
        self,
        customer_id: UUID,
    ) -> list[Conversation]:
        """
        Retrieve all conversations belonging to a tenant-owned customer.

        Customer existence is validated first so callers cannot use an
        arbitrary customer UUID as a cross-tenant lookup mechanism.
        """

        customer = await self.customer_repository.get_by_id(
            customer_id,
        )

        if customer is None:
            return []

        return await self.repository.get_by_customer(
            customer_id,
        )

    async def list_by_status(
        self,
        status: ConversationStatus,
    ) -> list[Conversation]:
        """
        Retrieve conversations filtered by lifecycle status.
        """

        return await self.repository.list_by_status(
            status,
        )

    async def list_by_channel(
        self,
        channel: ConversationChannel,
    ) -> list[Conversation]:
        """
        Retrieve conversations filtered by communication channel.
        """

        return await self.repository.list_by_channel(
            channel,
        )

    async def list_by_handling_mode(
        self,
        handling_mode: ConversationHandlingMode,
    ) -> list[Conversation]:
        """
        Retrieve conversations filtered by AI or human handling mode.
        """

        return await self.repository.list_by_handling_mode(
            handling_mode,
        )

    async def list_by_assigned_user(
        self,
        assigned_user_id: UUID,
    ) -> list[Conversation]:
        """
        Retrieve conversations assigned to a specific user.

        The repository applies the tenant boundary to the conversation
        query.

        Membership validation for assigned_user_id is intentionally not
        performed here because the current identity module does not yet
        expose a membership repository/service.
        """

        return await self.repository.list_by_assigned_user(
            assigned_user_id,
        )

    async def change_status(
        self,
        conversation_id: UUID,
        status: ConversationStatus,
    ) -> Conversation | None:
        """
        Change the lifecycle status of a conversation.

        Returns None when the conversation does not belong to the
        authorized tenant.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.status = status

        return await self._flush_and_refresh(
            conversation,
        )

    async def change_handling_mode(
        self,
        conversation_id: UUID,
        handling_mode: ConversationHandlingMode,
    ) -> Conversation | None:
        """
        Change a conversation between AI and human handling.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.handling_mode = handling_mode

        return await self._flush_and_refresh(
            conversation,
        )

    async def assign(
        self,
        conversation_id: UUID,
        assigned_user_id: UUID,
    ) -> Conversation | None:
        """
        Assign a conversation to a user.

        The conversation itself is tenant-scoped.

        Active-membership validation for the assigned user is deliberately
        deferred until the identity module exposes a dedicated
        membership lookup/service.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.assigned_user_id = assigned_user_id

        return await self._flush_and_refresh(
            conversation,
        )

    async def unassign(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        """
        Remove the current user assignment from a conversation.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.assigned_user_id = None

        return await self._flush_and_refresh(
            conversation,
        )

    async def increment_unread(
        self,
        conversation_id: UUID,
        amount: int = 1,
    ) -> Conversation | None:
        """
        Increase the unread message counter.

        The amount must be a positive integer.

        The validation is kept at the application-service boundary so
        callers cannot accidentally decrement or otherwise corrupt the
        unread counter through this operation.
        """

        if amount < 1:
            raise ValueError(
                "Unread increment amount must be greater than zero.",
            )

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.unread_count += amount

        return await self._flush_and_refresh(
            conversation,
        )

    async def clear_unread(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        """
        Clear all unread messages for a conversation.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.unread_count = 0

        return await self._flush_and_refresh(
            conversation,
        )

    async def update_last_message_at(
        self,
        conversation_id: UUID,
        timestamp: datetime,
    ) -> Conversation | None:
        """
        Update the last-message timestamp for a conversation.

        The timestamp is supplied by the application layer because message
        ingestion may need to preserve the provider event timestamp rather
        than replacing it with the local server clock.
        """

        conversation = await self.repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            return None

        conversation.last_message_at = timestamp

        return await self._flush_and_refresh(
            conversation,
        )

    async def _flush_and_refresh(
        self,
        conversation: Conversation,
    ) -> Conversation:
        """
        Persist an in-session conversation mutation and reload
        server-generated fields.

        Explicit refresh prevents asynchronous ORM attribute loading from
        occurring later during Pydantic response serialization.
        """

        await self.repository.db.flush()

        await self.repository.db.refresh(
            conversation,
        )

        return conversation