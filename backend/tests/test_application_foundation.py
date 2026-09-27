
"""
Tests for the Milestone 4D application foundation.

These tests verify:

- Pagination validation.
- Pagination calculations.
- Tenant-scoped SELECT statements.
- Tenant-scoped UPDATE statements.
- Tenant-scoped DELETE statements.

The tenant-scope tests inspect generated SQL structure without
requiring a new business module or database migration.
"""

from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, String, Table

from app.core.pagination import (
    PaginationParams,
    build_pagination_meta,
)
from app.core.tenant_scope import (
    tenant_scoped_delete,
    tenant_scoped_select,
    tenant_scoped_update,
)

metadata = MetaData()

# Test-only table representing the minimum structure required by
# tenant-owned resources.
test_customers = Table(
    "test_customers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("tenant_id", String(36), nullable=False),
    Column("name", String(255), nullable=False),
)


def test_pagination_defaults_are_safe():
    """Verify the default pagination values."""
    pagination = PaginationParams()

    assert pagination.page == 1
    assert pagination.page_size == 20
    assert pagination.offset == 0
    assert pagination.limit == 20


def test_pagination_calculates_offset():
    """Verify one-based page numbering produces the correct offset."""
    pagination = PaginationParams(
        page=3,
        page_size=25,
    )

    assert pagination.offset == 50
    assert pagination.limit == 25


def test_pagination_rejects_invalid_page():
    """Page numbers must start at one."""
    with pytest.raises(ValueError):
        PaginationParams(page=0)


def test_pagination_rejects_excessive_page_size():
    """Clients must not request arbitrarily large pages."""
    with pytest.raises(ValueError):
        PaginationParams(page_size=101)


def test_build_pagination_meta():
    """Verify metadata for a multi-page result set."""
    metadata_result = build_pagination_meta(
        page=2,
        page_size=20,
        total=45,
    )

    assert metadata_result.page == 2
    assert metadata_result.page_size == 20
    assert metadata_result.total == 45
    assert metadata_result.total_pages == 3
    assert metadata_result.has_next is True
    assert metadata_result.has_previous is True


def test_build_pagination_meta_for_empty_result():
    """Empty result sets should report zero total pages."""
    metadata_result = build_pagination_meta(
        page=1,
        page_size=20,
        total=0,
    )

    assert metadata_result.total_pages == 0
    assert metadata_result.has_next is False
    assert metadata_result.has_previous is False


def test_tenant_scoped_select_contains_tenant_predicate():
    """SELECT statements must contain the tenant boundary."""
    tenant_id = uuid4()

    statement = tenant_scoped_select(
        test_customers,
        tenant_id,
    )

    compiled = statement.compile()

    sql = str(compiled)

    assert "test_customers" in sql
    assert "tenant_id" in sql

    # The tenant ID must remain a bound SQL parameter rather than
    # being interpolated directly into the generated SQL.
    assert len(compiled.params) == 1


def test_tenant_scoped_update_contains_tenant_predicate():
    """UPDATE statements must contain the tenant boundary."""
    tenant_id = uuid4()

    statement = (
        tenant_scoped_update(
            test_customers,
            tenant_id,
        )
        .where(
            test_customers.c.id == str(uuid4()),
        )
        .values(
            name="Updated",
        )
    )

    compiled = statement.compile()

    sql = str(compiled)

    assert "UPDATE test_customers" in sql
    assert "tenant_id" in sql

    # Parameters are:
    # 1. tenant_id
    # 2. customer id
    # 3. updated name
    assert len(compiled.params) == 3


def test_tenant_scoped_delete_contains_tenant_predicate():
    """DELETE statements must contain the tenant boundary."""
    tenant_id = uuid4()

    statement = tenant_scoped_delete(
        test_customers,
        tenant_id,
    ).where(
        test_customers.c.id == str(uuid4()),
    )

    compiled = statement.compile()

    sql = str(compiled)

    assert "DELETE FROM test_customers" in sql
    assert "tenant_id" in sql

    # Parameters are:
    # 1. tenant_id
    # 2. customer id
    assert len(compiled.params) == 2
