"""
Create the tenant-scoped customers table.

Revision ID: 81412bbd7d59
Revises: 4a7c9d2e1f30

The PostgreSQL customer_status enum is explicitly managed by
this migration. SQLAlchemy must not attempt to create it again
when the customers table is created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "81412bbd7d59"
down_revision: str | Sequence[str] | None = "4a7c9d2e1f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Explicitly managed PostgreSQL enum.
#
# create_type=False prevents SQLAlchemy from automatically
# creating or dropping this type during table operations.
CUSTOMER_STATUS_ENUM = postgresql.ENUM(
    "active",
    "inactive",
    "blocked",
    "archived",
    name="customer_status",
    create_type=False,
)


def upgrade() -> None:
    """
    Create the customer enum, table, constraints and indexes.
    """

    # Create the enum exactly once.
    #
    # This is explicitly managed here so PostgreSQL does not receive
    # duplicate CREATE TYPE commands during table creation.
    CUSTOMER_STATUS_ENUM.create(
        op.get_bind(),
        checkfirst=False,
    )

    op.create_table(
        "customers",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "first_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "last_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "phone",
            sa.String(length=30),
            nullable=True,
        ),
        sa.Column(
            "email",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "company_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "status",
            CUSTOMER_STATUS_ENUM,
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "last_contacted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "email",
            name="uq_customer_tenant_email",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "phone",
            name="uq_customer_tenant_phone",
        ),
    )

    # Tenant-scoped query indexes.
    op.create_index(
        "ix_customers_tenant_created_at",
        "customers",
        ["tenant_id", "created_at"],
    )

    op.create_index(
        "ix_customers_tenant_id",
        "customers",
        ["tenant_id"],
    )

    op.create_index(
        "ix_customers_tenant_last_contacted_at",
        "customers",
        ["tenant_id", "last_contacted_at"],
    )

    op.create_index(
        "ix_customers_tenant_status",
        "customers",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    """
    Remove the customers table and its PostgreSQL enum.
    """

    op.drop_index(
        "ix_customers_tenant_status",
        table_name="customers",
    )

    op.drop_index(
        "ix_customers_tenant_last_contacted_at",
        table_name="customers",
    )

    op.drop_index(
        "ix_customers_tenant_id",
        table_name="customers",
    )

    op.drop_index(
        "ix_customers_tenant_created_at",
        table_name="customers",
    )

    op.drop_table("customers")

    # Drop the enum after the table no longer references it.
    CUSTOMER_STATUS_ENUM.drop(
        op.get_bind(),
        checkfirst=False,
    )