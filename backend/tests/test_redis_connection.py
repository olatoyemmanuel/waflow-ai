import pytest
import redis.asyncio as redis

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_redis_connection() -> None:
    settings = get_settings()

    client = redis.from_url(settings.redis_url)

    response = await client.ping()

    assert response is True

    await client.aclose()
