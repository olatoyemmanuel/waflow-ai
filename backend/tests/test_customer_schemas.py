"""
Tests for the customer API schemas.

These tests verify the API validation boundary independently of the
database, repository, service, and HTTP layers.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.customers.models import CustomerStatus
from app.modules.customers.schemas import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)


class TestCustomerCreate:
    """Tests for CustomerCreate."""

    def test_valid_payload(self) -> None:
        """A valid customer payload should be accepted."""

        payload = CustomerCreate(
            first_name="  Emmanuel  ",
            last_name=" Olatoye ",
            phone=" 08012345678 ",
            email="customer@example.com",
            company_name=" Example Ltd ",
            source=" WhatsApp ",
            notes=" Interested in the premium plan. ",
        )

        assert payload.first_name == "Emmanuel"
        assert payload.last_name == "Olatoye"
        assert payload.phone == "08012345678"
        assert str(payload.email) == "customer@example.com"
        assert payload.company_name == "Example Ltd"
        assert payload.source == "WhatsApp"
        assert payload.notes == "Interested in the premium plan."
        assert payload.status == CustomerStatus.ACTIVE

    def test_required_names_are_required(self) -> None:
        """First and last names must be provided."""

        with pytest.raises(ValidationError):
            CustomerCreate()

    def test_blank_first_name_is_rejected(self) -> None:
        """Whitespace-only first names must not pass validation."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="   ",
                last_name="Olatoye",
            )

    def test_blank_last_name_is_rejected(self) -> None:
        """Whitespace-only last names must not pass validation."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="   ",
            )

    def test_invalid_email_is_rejected(self) -> None:
        """Malformed email addresses must be rejected."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                email="not-an-email",
            )

    def test_field_length_limits_are_enforced(self) -> None:
        """Database-aligned maximum field lengths must be enforced."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="E" * 101,
                last_name="Olatoye",
            )

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                phone="1" * 31,
            )

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                company_name="C" * 256,
            )

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                source="S" * 101,
            )

    def test_empty_optional_strings_become_none(self) -> None:
        """Whitespace-only optional fields should normalize to None."""

        payload = CustomerCreate(
            first_name="Emmanuel",
            last_name="Olatoye",
            phone="   ",
            company_name="   ",
            source="   ",
            notes="   ",
        )

        assert payload.phone is None
        assert payload.company_name is None
        assert payload.source is None
        assert payload.notes is None

    def test_status_accepts_valid_enum_value(self) -> None:
        """Valid customer statuses should be accepted."""

        payload = CustomerCreate(
            first_name="Emmanuel",
            last_name="Olatoye",
            status=CustomerStatus.BLOCKED,
        )

        assert payload.status == CustomerStatus.BLOCKED

    def test_invalid_status_is_rejected(self) -> None:
        """Unknown customer statuses must be rejected."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                status="unknown",
            )

    def test_client_cannot_supply_tenant_id(self) -> None:
        """
        tenant_id must never be accepted from the client.

        The tenant is derived from authenticated TenantContext.
        """

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                tenant_id=uuid4(),  # type: ignore[call-arg]
            )

    def test_client_cannot_supply_id(self) -> None:
        """Customer IDs must be generated and managed by the server."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                id=uuid4(),  # type: ignore[call-arg]
            )

    def test_client_cannot_supply_timestamps(self) -> None:
        """Database-managed timestamps cannot be client-controlled."""

        with pytest.raises(ValidationError):
            CustomerCreate(
                first_name="Emmanuel",
                last_name="Olatoye",
                created_at=datetime.now(timezone.utc),  # type: ignore[call-arg]
            )


class TestCustomerUpdate:
    """Tests for CustomerUpdate."""

    def test_partial_update_is_allowed(self) -> None:
        """Only the fields being changed need to be supplied."""

        payload = CustomerUpdate(
            first_name=" Emmanuel ",
        )

        assert payload.first_name == "Emmanuel"
        assert payload.last_name is None
        assert payload.email is None

    def test_empty_update_payload_is_allowed_at_schema_level(self) -> None:
        """
        The schema permits an empty PATCH payload.

        The application service/API layer can decide whether an empty
        update should be rejected as a business rule.
        """

        payload = CustomerUpdate()

        assert payload.model_dump(exclude_unset=True) == {}

    def test_invalid_email_is_rejected(self) -> None:
        """Malformed update email addresses must be rejected."""

        with pytest.raises(ValidationError):
            CustomerUpdate(email="invalid-email")

    def test_invalid_status_is_rejected(self) -> None:
        """Unknown update statuses must be rejected."""

        with pytest.raises(ValidationError):
            CustomerUpdate(status="unknown")

    def test_client_cannot_change_tenant(self) -> None:
        """tenant_id cannot be supplied in an update."""

        with pytest.raises(ValidationError):
            CustomerUpdate(
                tenant_id=uuid4(),  # type: ignore[call-arg]
            )

    def test_client_cannot_change_customer_id(self) -> None:
        """id cannot be supplied in an update."""

        with pytest.raises(ValidationError):
            CustomerUpdate(
                id=uuid4(),  # type: ignore[call-arg]
            )


class TestCustomerResponse:
    """Tests for CustomerResponse."""

    def test_response_accepts_database_representation(self) -> None:
        """The response schema should serialize customer model attributes."""

        customer_id = uuid4()
        now = datetime.now(timezone.utc)

        payload = CustomerResponse(
            id=customer_id,
            first_name="Emmanuel",
            last_name="Olatoye",
            phone="08012345678",
            email="customer@example.com",
            company_name="Example Ltd",
            status=CustomerStatus.ACTIVE,
            source="WhatsApp",
            notes=None,
            last_contacted_at=None,
            created_at=now,
            updated_at=now,
        )

        assert payload.id == customer_id
        assert payload.status == CustomerStatus.ACTIVE
        assert payload.created_at == now
        assert payload.updated_at == now


class TestCustomerListResponse:
    """Tests for CustomerListResponse."""

    def test_paginated_response(self) -> None:
        """A valid paginated customer collection should be accepted."""

        now = datetime.now(timezone.utc)

        customer = CustomerResponse(
            id=uuid4(),
            first_name="Emmanuel",
            last_name="Olatoye",
            phone=None,
            email=None,
            company_name=None,
            status=CustomerStatus.ACTIVE,
            source=None,
            notes=None,
            last_contacted_at=None,
            created_at=now,
            updated_at=now,
        )

        response = CustomerListResponse(
            items=[customer],
            total=1,
            page=1,
            page_size=20,
            pages=1,
        )

        assert response.total == 1
        assert response.page == 1
        assert response.page_size == 20
        assert response.pages == 1
        assert len(response.items) == 1