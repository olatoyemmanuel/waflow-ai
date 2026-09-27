"""
WAFlow AI FastAPI application entry point.

Responsibilities:
- Create the FastAPI application.
- Configure development CORS.
- Register the versioned API router.
- Expose the health endpoint.

Production CORS configuration should eventually come from
environment configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router

app = FastAPI(
    title="WAFlow AI API",
    version="0.1.0",
    description="Multi-tenant WhatsApp AI automation SaaS API",
)


# Frontend origins allowed to communicate with the API.
#
# During local development:
# - Vite frontend: http://localhost:5173
# - FastAPI backend: http://localhost:8000
#
# These should move into environment configuration before
# production deployment.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# Configure browser cross-origin access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register the versioned API.
#
# Authentication endpoints will therefore be available under:
# /api/v1/auth/...
app.include_router(
    api_router,
)


@app.get("/health")
async def health_check() -> dict[str, object]:
    """
    Return the current API health status.

    This endpoint remains outside /api/v1 because infrastructure
    health checks should remain stable across API versions.
    """

    return {
        "success": True,
        "data": {
            "status": "healthy",
        },
    }