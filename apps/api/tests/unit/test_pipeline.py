import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus, Integration, IntegrationProvider, Proposal
from openforce.db.session import SessionLocal
from openforce.proposals.service import process_one_email, process_unprocessed_batch


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(Proposal))
        s.execute(delete(Email))
        s.execute(delete(Integration).where(Integration.provider == IntegrationProvider.salesforce))
        s.commit()
    eng.dispose()


def _seed_sf_integration() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.add(
            Integration(
                provider=IntegrationProvider.salesforce,
                access_token="t",
                refresh_token="r",
                instance_url="https://x.my.salesforce.com",
            )
        )
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe()
    _seed_sf_integration()


def teardown_function(_):
    _wipe()


async def _seed_email(session, msg_id: str) -> Email:
    email = Email(
        gmail_msg_id=msg_id,
        thread_id="t",
        sender="sam@acme.test",
        subject="x",
        body_text="ping",
        received_at=datetime.now(timezone.utc),
    )
    session.add(email)
    await session.commit()
    await session.refresh(email)
    return email


def _fake_openai(responses):
    def factory():
        c = MagicMock()
        c.chat.completions.create.side_effect = responses
        return c
    return factory


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _resp(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_process_one_email_flips_status_to_irrelevant():
    sf_factory = lambda _i: MagicMock()
    openai_factory = _fake_openai([_resp(_msg(content="no_action"))])

    async with SessionLocal() as s:
        email = await _seed_email(s, "m-irrel")
        status = await process_one_email(
            s, email.id, sf_client_factory=sf_factory, openai_client_factory=openai_factory
        )
        assert status == EmailStatus.irrelevant
        await s.refresh(email)
        assert email.status == EmailStatus.irrelevant


@pytest.mark.asyncio
async def test_process_unprocessed_batch_processes_all_pending():
    sf_factory = lambda _i: MagicMock()
    # 2 emails -> 2 calls each returning no_action
    openai_factory = _fake_openai(
        [_resp(_msg(content="no_action")), _resp(_msg(content="no_action"))]
    )

    async with SessionLocal() as s:
        await _seed_email(s, "m1")
        await _seed_email(s, "m2")
        n = await process_unprocessed_batch(
            s, sf_client_factory=sf_factory, openai_client_factory=openai_factory
        )
        assert n == 2

        rows = (await s.execute(select(Email))).scalars().all()
        assert all(r.status == EmailStatus.irrelevant for r in rows)


@pytest.mark.asyncio
async def test_process_one_email_marks_extraction_failed_on_exception():
    def boom(_i):
        m = MagicMock()
        return m

    def factory():
        c = MagicMock()
        c.chat.completions.create.side_effect = RuntimeError("openai down")
        return c

    async with SessionLocal() as s:
        email = await _seed_email(s, "m-fail")
        status = await process_one_email(
            s, email.id, sf_client_factory=boom, openai_client_factory=factory
        )
        assert status == EmailStatus.extraction_failed
        await s.refresh(email)
        assert email.error == "openai down"
