"""
WAFlow AI API router.

All versioned API routers are registered here.

Keeping the versioning in one place makes it easier to introduce
future API versions without restructuring every feature module.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router

api_router = APIRouter(
    prefix="/api/v1",
)


# Authentication and identity endpoints.
api_router.include_router(
    auth_router,
)
