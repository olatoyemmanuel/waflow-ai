from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.modules.identity.models import Permission, Role, RolePermission

ROLES = {
    "OWNER": "Full access to the tenant.",
    "ADMIN": "Administrative access to the tenant.",
    "MANAGER": "Management access to operational resources.",
    "AGENT": "Customer support and conversation access.",
    "VIEWER": "Read-only access to permitted resources.",
}


PERMISSIONS = {
    "customers.read": "View customers.",
    "customers.create": "Create customers.",
    "customers.update": "Update customers.",
    "customers.delete": "Delete customers.",
    "customers.assign": "Assign customers.",

    "conversations.read": "View conversations.",
    "conversations.reply": "Reply to conversations.",
    "conversations.assign": "Assign conversations.",
    "conversations.resolve": "Resolve conversations.",
    "conversations.takeover": "Take over AI conversations.",

    "whatsapp.read": "View WhatsApp accounts.",
    "whatsapp.manage": "Manage WhatsApp accounts.",
    "whatsapp.send": "Send WhatsApp messages.",

    "ai.read": "View AI configuration.",
    "ai.manage": "Manage AI configuration.",
    "ai.test": "Test AI agents.",

    "knowledge.read": "View knowledge documents.",
    "knowledge.upload": "Upload knowledge documents.",
    "knowledge.update": "Update knowledge documents.",
    "knowledge.delete": "Delete knowledge documents.",
    "knowledge.process": "Process knowledge documents.",

    "workflows.read": "View workflows.",
    "workflows.create": "Create workflows.",
    "workflows.update": "Update workflows.",
    "workflows.delete": "Delete workflows.",
    "workflows.activate": "Activate workflows.",

    "appointments.read": "View appointments.",
    "appointments.create": "Create appointments.",
    "appointments.update": "Update appointments.",
    "appointments.cancel": "Cancel appointments.",

    "analytics.read": "View analytics.",
    "analytics.export": "Export analytics.",

    "billing.read": "View billing information.",
    "billing.manage": "Manage billing.",
    "billing.change_plan": "Change subscription plan.",

    "team.read": "View team members.",
    "team.invite": "Invite team members.",
    "team.update": "Update team members.",
    "team.remove": "Remove team members.",
    "team.change_role": "Change team member roles.",

    "settings.read": "View tenant settings.",
    "settings.update": "Update tenant settings.",

    "api_keys.read": "View API keys.",
    "api_keys.create": "Create API keys.",
    "api_keys.revoke": "Revoke API keys.",

    "audit.read": "View audit logs.",
}


ROLE_PERMISSIONS = {
    "OWNER": set(PERMISSIONS),

    "ADMIN": {
        permission
        for permission in PERMISSIONS
        if permission != "billing.change_plan"
    },

    "MANAGER": {
        "customers.read",
        "customers.create",
        "customers.update",
        "customers.assign",

        "conversations.read",
        "conversations.reply",
        "conversations.assign",
        "conversations.resolve",
        "conversations.takeover",

        "whatsapp.read",
        "whatsapp.send",

        "ai.read",
        "ai.test",

        "knowledge.read",
        "knowledge.upload",
        "knowledge.update",
        "knowledge.process",

        "workflows.read",
        "workflows.create",
        "workflows.update",
        "workflows.activate",

        "appointments.read",
        "appointments.create",
        "appointments.update",
        "appointments.cancel",

        "analytics.read",
        "analytics.export",

        "team.read",
        "team.invite",
        "team.update",

        "settings.read",
    },

    "AGENT": {
        "customers.read",
        "customers.create",
        "customers.update",

        "conversations.read",
        "conversations.reply",
        "conversations.resolve",
        "conversations.takeover",

        "whatsapp.read",
        "whatsapp.send",

        "ai.read",

        "knowledge.read",

        "appointments.read",
        "appointments.create",
        "appointments.update",
        "appointments.cancel",

        "analytics.read",

        "team.read",

        "settings.read",
    },

    "VIEWER": {
        "customers.read",
        "conversations.read",
        "whatsapp.read",
        "ai.read",
        "knowledge.read",
        "workflows.read",
        "appointments.read",
        "analytics.read",
        "team.read",
        "settings.read",
    },
}


async def seed_rbac(session: AsyncSession) -> None:
    """Create the default roles, permissions, and role mappings."""

    permissions_by_name: dict[str, Permission] = {}

    # ---------------------------------------------------------
    # Permissions
    # ---------------------------------------------------------
    for name, description in PERMISSIONS.items():
        result = await session.execute(
            select(Permission).where(Permission.name == name)
        )

        permission = result.scalar_one_or_none()

        if permission is None:
            permission = Permission(
                name=name,
                description=description,
            )
            session.add(permission)
            await session.flush()

        permissions_by_name[name] = permission

    # ---------------------------------------------------------
    # Roles
    # ---------------------------------------------------------
    roles_by_name: dict[str, Role] = {}

    for name, description in ROLES.items():
        result = await session.execute(
            select(Role).where(Role.name == name)
        )

        role = result.scalar_one_or_none()

        if role is None:
            role = Role(
                name=name,
                description=description,
            )
            session.add(role)
            await session.flush()

        roles_by_name[name] = role

    # ---------------------------------------------------------
    # Role permissions
    #
    # Use PostgreSQL ON CONFLICT DO NOTHING so the seed
    # remains idempotent even if executed repeatedly.
    # ---------------------------------------------------------
    role_permission_rows = []

    for role_name, permission_names in ROLE_PERMISSIONS.items():
        role = roles_by_name[role_name]

        for permission_name in permission_names:
            permission = permissions_by_name[permission_name]

            role_permission_rows.append(
                {
                    "role_id": role.id,
                    "permission_id": permission.id,
                }
            )

    if role_permission_rows:
        statement = (
            insert(RolePermission)
            .values(role_permission_rows)
            .on_conflict_do_nothing(
                index_elements=[
                    RolePermission.role_id,
                    RolePermission.permission_id,
                ]
            )
        )

        await session.execute(statement)

    await session.commit()


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)
        print("RBAC seed completed successfully.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())