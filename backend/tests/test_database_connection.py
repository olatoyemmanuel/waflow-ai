import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_database_connection() -> None:
    from app.core.database import engine

    assert isinstance(engine, AsyncEngine)

    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    await engine.dispose()
