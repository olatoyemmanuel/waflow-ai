"""
WAFlow AI FastAPI application entry point.

This module creates the FastAPI application and configures
cross-origin access for the frontend during development.

Production CORS origins should eventually come from environment
configuration rather than being hard-coded.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="WAFlow AI API",
    version="0.1.0",
    description="Multi-tenant WhatsApp AI automation SaaS API",
)


# Frontend origins allowed to communicate with the API.
#
# During local development:
# - Vite frontend runs on port 5173
# - FastAPI runs on port 8000
#
# We will move these origins into environment configuration
# before production deployment.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# Configure CORS middleware.
#
# This allows the browser-based frontend to make API requests
# to the FastAPI backend running on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, object]:
    """
    Return the current API health status.

    This endpoint is intentionally simple because it will be used
    by infrastructure monitoring and by the frontend integration
    test for our first end-to-end API connection.
    """

    return {
        "success": True,
        "data": {
            "status": "healthy",
        },
    }