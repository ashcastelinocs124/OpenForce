import pytest
from sqlalchemy import text

from openforce.db.session import SessionLocal


@pytest.mark.asyncio
async def test_can_connect_and_select_one():
    async with SessionLocal() as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
