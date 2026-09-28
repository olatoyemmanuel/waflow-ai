"""
Pagination primitives for WAFlow AI APIs.

This module provides reusable, validated pagination parameters for
tenant-scoped list endpoints.

Pagination is intentionally kept independent from any particular
business module so Customers, Conversations, Knowledge Base,
Appointments, Campaigns, and other modules can use the same API
contract.
"""

from pydantic import BaseModel, Field

# Security limit for SQL OFFSET pagination.
#
# A very large page number can result in an unnecessarily expensive
# database query. Keeping this limit at module level prevents Pydantic
# from treating it as a model field.
MAX_PAGE = 1_000


class PaginationParams(BaseModel):
    """
    Validated pagination parameters.

    `page` is one-based.
    `page_size` is deliberately capped to prevent clients from
    requesting excessively large result sets.
    """

    page: int = Field(
        default=1,
        ge=1,
        le=MAX_PAGE,
        description=(
            f"One-based page number. Maximum is {MAX_PAGE}."
        ),
    )

    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of records returned per page.",
    )

    @property
    def offset(self) -> int:
        """
        Calculate the SQL offset for the current page.
        """

        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """
        Return the SQL LIMIT value.

        Keeping this as a property makes service and repository code
        explicit and readable.
        """

        return self.page_size


class PaginationMeta(BaseModel):
    """
    Pagination metadata returned with list responses.
    """

    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


def build_pagination_meta(
    *,
    page: int,
    page_size: int,
    total: int,
) -> PaginationMeta:
    """
    Build pagination metadata from a total record count.

    Args:
        page: Current one-based page.
        page_size: Number of records requested per page.
        total: Total number of matching records.

    Returns:
        Pagination metadata suitable for an API response.
    """

    total_pages = (
        (total + page_size - 1) // page_size
        if total > 0
        else 0
    )

    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1 and total_pages > 0,
    )