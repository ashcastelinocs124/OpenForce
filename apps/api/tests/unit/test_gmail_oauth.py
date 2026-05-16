import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import Integration, IntegrationProvider
from openforce.main import app


def _wipe_gmail_integration() -> None:
    sync_url = get_settings().database_url_sync
    if not sync_url:
        return
    eng = create_engine(sync_url)
    with Session(eng) as s:
        s.execute(delete(Integration).where(Integration.provider == IntegrationProvider.gmail))
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe_gmail_integration()


def teardown_function(_):
    _wipe_gmail_integration()


def test_gmail_start_returns_url():
    with TestClient(app) as client:
        r = client.get("/auth/gmail/start")
        assert r.status_code == 200
        url = r.json()["url"]
        assert "accounts.google.com" in url
        assert "scope=https" in url
        assert "access_type=offline" in url


def test_gmail_callback_persists_tokens():
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post("https://oauth2.googleapis.com/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "ya29.test",
                    "refresh_token": "1//refresh",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )
        with TestClient(app) as client:
            r = client.get("/auth/gmail/callback?code=abc")
            assert r.status_code == 200
            assert r.json() == {"status": "connected"}

    sync_url = get_settings().database_url_sync
    eng = create_engine(sync_url)
    with Session(eng) as s:
        rows = s.execute(
            delete(Integration)
            .where(Integration.provider == IntegrationProvider.gmail)
            .returning(Integration.access_token, Integration.refresh_token)
        ).fetchall()
        s.commit()
        assert rows
        assert rows[0][0] == "ya29.test"
        assert rows[0][1] == "1//refresh"
    eng.dispose()
