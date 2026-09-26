from fastapi import FastAPI

app = FastAPI(
    title="WAFlow AI API",
    version="0.1.0",
    description="Multi-tenant WhatsApp AI automation SaaS API",
)


@app.get("/health")
async def health_check() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "status": "healthy",
        },
    }
