import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import Integration, IntegrationProvider
from openforce.main import app


def _wipe_sf_integration() -> None:
    sync_url = get_settings().database_url_sync
    eng = create_engine(sync_url)
    with Session(eng) as s:
        s.execute(delete(Integration).where(Integration.provider == IntegrationProvider.salesforce))
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe_sf_integration()


def teardown_function(_):
    _wipe_sf_integration()


def test_sf_start_returns_authorize_url():
    with TestClient(app) as client:
        r = client.get("/auth/salesforce/start")
        assert r.status_code == 200
        url = r.json()["url"]
        assert "/services/oauth2/authorize" in url
        assert "response_type=code" in url


@pytest.mark.asyncio
async def test_sf_callback_persists_tokens():
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post("https://login.salesforce.com/services/oauth2/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "a-token",
                    "refresh_token": "r-token",
                    "instance_url": "https://example.my.salesforce.com",
                },
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/auth/salesforce/callback?code=abc")
            assert r.status_code == 200
            assert r.json() == {"status": "connected"}

    sync_url = get_settings().database_url_sync
    eng = create_engine(sync_url)
    with Session(eng) as s:
        rows = s.execute(
            select(Integration.access_token, Integration.instance_url).where(
                Integration.provider == IntegrationProvider.salesforce
            )
        ).fetchall()
        assert rows
        assert rows[0][0] == "a-token"
        assert rows[0][1] == "https://example.my.salesforce.com"
    eng.dispose()
