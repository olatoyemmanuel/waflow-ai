"""
WAFlow AI API router.

All versioned API routers are registered here.

Keeping API versioning in one place makes it easier to introduce future
API versions without restructuring individual feature modules.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.customers.router import router as customers_router

api_router = APIRouter(
    prefix="/api/v1",
)


# Authentication and identity endpoints.
api_router.include_router(
    auth_router,
)


# Customer/CRM endpoints.
#
# The customer router owns its endpoint-level authentication,
# tenant-membership, and permission dependencies.
api_router.include_router(
    customers_router,
)