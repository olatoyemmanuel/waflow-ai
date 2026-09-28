"""
Tests for the Milestone 4E Customer/CRM domain model.

These tests verify the structural properties of the Customer model
without requiring a database migration or live PostgreSQL connection.

The tests focus on:

- Tenant ownership.
- Required customer fields.
- Customer status defaults.
- Tenant-scoped uniqueness constraints.
- Tenant-scoped indexes.
- Timestamp configuration.
"""

import uuid

from app.modules.customers.models import Customer, CustomerStatus


def test_customer_has_tenant_id():
    """
    Every customer must explicitly belong to a tenant.
    """
    column = Customer.__table__.c.tenant_id

    assert column.nullable is False
    assert column.foreign_keys

    foreign_key = next(
        iter(column.foreign_keys),
    )

    assert foreign_key.target_fullname == "tenants.id"


def test_customer_has_required_identity_fields():
    """
    Customer names are required identity fields.
    """
    table = Customer.__table__

    assert table.c.first_name.nullable is False
    assert table.c.last_name.nullable is False

    assert table.c.phone.nullable is True
    assert table.c.email.nullable is True


def test_customer_status_defaults_to_active():
    """
    New customers should default to ACTIVE.
    """
    customer = Customer(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        first_name="John",
        last_name="Doe",
    )

    # SQLAlchemy applies Python-side defaults when the object is
    # inserted/flushed rather than immediately during construction.
    #
    # Therefore the model's configured default is inspected directly.
    default = Customer.__table__.c.status.default

    assert default is not None
    assert default.arg == CustomerStatus.ACTIVE

    assert customer.status is None


def test_customer_has_tenant_scoped_phone_uniqueness():
    """
    Phone numbers must be unique within a tenant, not globally.
    """
    constraint_names = {
        constraint.name
        for constraint in Customer.__table__.constraints
    }

    assert "uq_customer_tenant_phone" in constraint_names


def test_customer_has_tenant_scoped_email_uniqueness():
    """
    Email addresses must be unique within a tenant, not globally.
    """
    constraint_names = {
        constraint.name
        for constraint in Customer.__table__.constraints
    }

    assert "uq_customer_tenant_email" in constraint_names


def test_customer_has_tenant_scoped_indexes():
    """
    Common CRM queries should have tenant-first indexes.
    """
    index_names = {
        index.name
        for index in Customer.__table__.indexes
    }

    assert "ix_customers_tenant_status" in index_names
    assert "ix_customers_tenant_created_at" in index_names
    assert "ix_customers_tenant_last_contacted_at" in index_names


def test_customer_has_audit_timestamps():
    """
    Customer records must have created and updated timestamps.
    """
    table = Customer.__table__

    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False

    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None


def test_customer_status_enum_values_are_stable():
    """
    Verify the persisted customer status vocabulary.
    """
    assert CustomerStatus.ACTIVE.value == "active"
    assert CustomerStatus.INACTIVE.value == "inactive"
    assert CustomerStatus.BLOCKED.value == "blocked"
    assert CustomerStatus.ARCHIVED.value == "archived"