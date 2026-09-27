"""
Tenant-scoped database query helpers.

WAFlow AI is a multi-tenant application. Every tenant-owned database
operation must be explicitly scoped to the authorized tenant.

This module provides reusable SQLAlchemy helpers that make the tenant
boundary explicit in application and repository code.

Security principle:

    The authenticated TenantContext determines the tenant scope.

    Client-provided tenant IDs must never be used directly as proof
    of authorization.

These helpers do not perform authorization themselves. Authorization
must already have been established by the authentication and
authorization dependencies before these helpers are used.

The helpers support both:

- SQLAlchemy ORM models, for example Customer.tenant_id.
- SQLAlchemy Core Table objects, for example table.c.tenant_id.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.sql import Delete, Select, Update


def _tenant_column(model: Any) -> Any:
    """
    Resolve the tenant_id column from an ORM model or SQLAlchemy Table.

    ORM models expose mapped attributes directly:

        Customer.tenant_id

    SQLAlchemy Core Table objects expose columns through `.c`:

        customers.c.tenant_id

    Args:
        model: SQLAlchemy ORM model or Core Table.

    Returns:
        The model's tenant_id column.

    Raises:
        AttributeError: If the supplied model does not expose a
            tenant_id column.
    """
    tenant_column = getattr(model, "tenant_id", None)

    if tenant_column is not None:
        return tenant_column

    columns = getattr(model, "c", None)

    if columns is not None:
        tenant_column = getattr(columns, "tenant_id", None)

        if tenant_column is not None:
            return tenant_column

    raise AttributeError(
        "Tenant-scoped models must define a tenant_id column.",
    )


def tenant_scoped_select(
    model: Any,
    tenant_id: UUID,
) -> Select:
    """
    Build a SELECT statement restricted to one tenant.

    The model must expose a `tenant_id` column.

    Example with an ORM model:

        statement = tenant_scoped_select(
            Customer,
            tenant_context.tenant_id,
        )

    Example with a SQLAlchemy Core table:

        statement = tenant_scoped_select(
            customers,
            tenant_context.tenant_id,
        )

    The resulting query is conceptually:

        SELECT ...
        FROM customers
        WHERE customers.tenant_id = :tenant_id

    Args:
        model: SQLAlchemy ORM model or Core Table containing tenant_id.
        tenant_id: Authorized tenant UUID.

    Returns:
        A SQLAlchemy SELECT statement scoped to tenant_id.
    """
    return select(model).where(
        _tenant_column(model) == tenant_id,
    )


def tenant_scoped_update(
    model: Any,
    tenant_id: UUID,
) -> Update:
    """
    Build an UPDATE statement restricted to one tenant.

    Additional filters must be added by the caller.

    Example:

        statement = (
            tenant_scoped_update(
                Customer,
                tenant_context.tenant_id,
            )
            .where(Customer.id == customer_id)
            .values(name="Updated Customer")
        )

    The tenant predicate is always included in the UPDATE statement.

    Args:
        model: SQLAlchemy ORM model or Core Table containing tenant_id.
        tenant_id: Authorized tenant UUID.

    Returns:
        A SQLAlchemy UPDATE statement scoped to tenant_id.
    """
    return update(model).where(
        _tenant_column(model) == tenant_id,
    )


def tenant_scoped_delete(
    model: Any,
    tenant_id: UUID,
) -> Delete:
    """
    Build a DELETE statement restricted to one tenant.

    Additional filters must be added by the caller.

    Example:

        statement = (
            tenant_scoped_delete(
                Customer,
                tenant_context.tenant_id,
            )
            .where(Customer.id == customer_id)
        )

    The tenant predicate is always included in the DELETE statement.

    Args:
        model: SQLAlchemy ORM model or Core Table containing tenant_id.
        tenant_id: Authorized tenant UUID.

    Returns:
        A SQLAlchemy DELETE statement scoped to tenant_id.
    """
    return delete(model).where(
        _tenant_column(model) == tenant_id,
    )
