"""
WAFlow AI customer/CRM API routes.

All customer endpoints are tenant-scoped.

Security flow:

    JWT
      ↓
    Active User
      ↓
    Active Tenant Membership
      ↓
    Database Permission
      ↓
    TenantContext
      ↓
    CustomerService
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.modules.auth.dependencies import (
    CurrentTenantContext,
    require_permission,
)
from app.modules.customers.models import CustomerStatus
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.modules.customers.service import CustomerService

router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)


async def get_customer_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_context: CurrentTenantContext,
) -> CustomerService:
    """
    Build a CustomerService bound to the authenticated tenant.

    The tenant ID comes exclusively from TenantContext.
    """

    repository = CustomerRepository(
        db=db,
        tenant_id=tenant_context.tenant_id,
    )

    return CustomerService(
        repository=repository,
        tenant_context=tenant_context,
    )


CustomerServiceDependency = Annotated[
    CustomerService,
    Depends(get_customer_service),
]


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_permission("customers.create")),
    ],
)
async def create_customer(
    payload: CustomerCreate,
    service: CustomerServiceDependency,
) -> dict:
    """
    Create a customer inside the authenticated tenant.
    """

    try:
        customer = await service.create(payload)

        await service.repository.db.commit()

    except ValueError as exc:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except IntegrityError as exc:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A customer with the supplied contact information "
                "already exists."
            ),
        ) from exc

    return {
        "success": True,
        "data": CustomerResponse.model_validate(
            customer,
        ).model_dump(mode="json"),
    }


@router.get(
    "",
    response_model=dict,
    dependencies=[
        Depends(require_permission("customers.read")),
    ],
)
async def list_customers(
    service: CustomerServiceDependency,
    pagination: Annotated[
        PaginationParams,
        Depends(),
    ],
    search: Annotated[
        str | None,
        Query(
            max_length=255,
            description=(
                "Search first name, last name, email, phone, "
                "or company name."
            ),
        ),
    ] = None,
    customer_status: Annotated[
        CustomerStatus | None,
        Query(
            alias="status",
            description="Filter customers by lifecycle status.",
        ),
    ] = None,
) -> dict:
    """
    List customers belonging to the authenticated tenant.

    Clients may use either `search` or `status`, but not both.
    """

    if search is not None and customer_status is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Use either the search parameter or the status parameter, "
                "not both."
            ),
        )

    if search is not None:
        customers, pagination_meta = await service.search(
            query=search,
            pagination=pagination,
        )

    elif customer_status is not None:
        customers, pagination_meta = await service.list_by_status(
            status=customer_status,
            pagination=pagination,
        )

    else:
        customers, pagination_meta = await service.list(
            pagination,
        )

    response = CustomerListResponse(
        items=[
            CustomerResponse.model_validate(customer)
            for customer in customers
        ],
        total=pagination_meta.total,
        page=pagination_meta.page,
        page_size=pagination_meta.page_size,
        pages=pagination_meta.total_pages,
    )

    return {
        "success": True,
        "data": response.model_dump(mode="json"),
    }


@router.get(
    "/{customer_id}",
    response_model=dict,
    dependencies=[
        Depends(require_permission("customers.read")),
    ],
)
async def get_customer(
    customer_id: UUID,
    service: CustomerServiceDependency,
) -> dict:
    """
    Retrieve one customer from the authenticated tenant.
    """

    customer = await service.get(customer_id)

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    return {
        "success": True,
        "data": CustomerResponse.model_validate(
            customer,
        ).model_dump(mode="json"),
    }


@router.patch(
    "/{customer_id}",
    response_model=dict,
    dependencies=[
        Depends(require_permission("customers.update")),
    ],
)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    service: CustomerServiceDependency,
) -> dict:
    """
    Update a customer inside the authenticated tenant.
    """

    try:
        customer = await service.update(
            customer_id=customer_id,
            data=payload,
        )

        if customer is None:
            await service.repository.db.rollback()

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found.",
            )

        await service.repository.db.commit()

    except HTTPException:
        raise

    except ValueError as exc:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except IntegrityError as exc:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The customer could not be updated because the supplied "
                "contact information already exists."
            ),
        ) from exc

    return {
        "success": True,
        "data": CustomerResponse.model_validate(
            customer,
        ).model_dump(mode="json"),
    }


@router.post(
    "/{customer_id}/archive",
    response_model=dict,
    dependencies=[
        Depends(require_permission("customers.delete")),
    ],
)
async def archive_customer(
    customer_id: UUID,
    service: CustomerServiceDependency,
) -> dict:
    """
    Archive a customer without physically deleting its database row.

    The existing RBAC model uses customers.delete for this lifecycle
    operation.
    """

    customer = await service.archive(customer_id)

    if customer is None:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    await service.repository.db.commit()

    return {
        "success": True,
        "data": CustomerResponse.model_validate(
            customer,
        ).model_dump(mode="json"),
    }


@router.post(
    "/{customer_id}/restore",
    response_model=dict,
    dependencies=[
        Depends(require_permission("customers.update")),
    ],
)
async def restore_customer(
    customer_id: UUID,
    service: CustomerServiceDependency,
) -> dict:
    """
    Restore a customer to ACTIVE status.

    The existing RBAC model uses customers.update for restoration.
    """

    customer = await service.restore(customer_id)

    if customer is None:
        await service.repository.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    await service.repository.db.commit()

    return {
        "success": True,
        "data": CustomerResponse.model_validate(
            customer,
        ).model_dump(mode="json"),
    }