from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import Email, Integration, IntegrationProvider
from openforce.db.session import SessionLocal
from openforce.gmail.client import GmailMessage
from openforce.gmail.ingest import ingest_new_emails


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(Email))
        s.execute(delete(Integration).where(Integration.provider == IntegrationProvider.gmail))
        s.commit()
    eng.dispose()


def _seed_gmail_integration(history_id: str | None = None) -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.add(
            Integration(
                provider=IntegrationProvider.gmail,
                access_token="t",
                refresh_token="r",
                history_id=history_id,
            )
        )
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe()


def teardown_function(_):
    _wipe()


def _fake_message(msg_id: str) -> GmailMessage:
    return GmailMessage(
        msg_id=msg_id,
        thread_id=f"t-{msg_id}",
        sender="sam@acme.test",
        subject="hello",
        body_text="body",
        received_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_ingest_inserts_new_emails():
    _seed_gmail_integration(history_id="100")

    fake_client = MagicMock()
    fake_client.list_history_since.return_value = (["m1", "m2"], "200")
    fake_client.get_message.side_effect = lambda mid: _fake_message(mid)

    async with SessionLocal() as s:
        inserted = await ingest_new_emails(s, client_factory=lambda _i: fake_client)
        assert inserted == 2

        rows = (await s.execute(select(Email))).scalars().all()
        assert {r.gmail_msg_id for r in rows} == {"m1", "m2"}


@pytest.mark.asyncio
async def test_ingest_is_idempotent_on_duplicates():
    _seed_gmail_integration(history_id="100")

    fake_client = MagicMock()
    fake_client.list_history_since.return_value = (["m1", "m1", "m2"], "200")
    fake_client.get_message.side_effect = lambda mid: _fake_message(mid)

    async with SessionLocal() as s:
        inserted = await ingest_new_emails(s, client_factory=lambda _i: fake_client)
        # only 2 unique IDs inserted; second m1 hits the unique constraint
        assert inserted == 2
        rows = (await s.execute(select(Email))).scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_ingest_skips_when_needs_reauth():
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.add(
            Integration(
                provider=IntegrationProvider.gmail,
                access_token="t",
                refresh_token="r",
                needs_reauth=True,
            )
        )
        s.commit()
    eng.dispose()

    fake_client = MagicMock()

    async with SessionLocal() as s:
        inserted = await ingest_new_emails(s, client_factory=lambda _i: fake_client)
        assert inserted == 0
    fake_client.list_history_since.assert_not_called()
