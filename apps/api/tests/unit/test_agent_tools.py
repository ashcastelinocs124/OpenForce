import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.agent.tools import ToolContext, handle_tool_call
from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus, Proposal, ProposalStatus
from openforce.db.session import SessionLocal


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(Proposal))
        s.execute(delete(Email))
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe()


def teardown_function(_):
    _wipe()


async def _seed_email(session) -> Email:
    email = Email(
        gmail_msg_id=f"msg-{datetime.now(timezone.utc).isoformat()}",
        thread_id="t-1",
        sender="sam@acme.test",
        subject="hi",
        body_text="ping",
        received_at=datetime.now(timezone.utc),
        status=EmailStatus.unprocessed,
    )
    session.add(email)
    await session.commit()
    await session.refresh(email)
    return email


@pytest.mark.asyncio
async def test_search_contacts_returns_sf_results():
    sf = MagicMock()
    sf.search_contacts.return_value = [{"Id": "003xx", "Email": "sam@acme.test"}]

    async with SessionLocal() as s:
        email = await _seed_email(s)
        ctx = ToolContext(sf=sf, session=s, email_id=email.id)
        result = await handle_tool_call(ctx, "search_salesforce_contacts", json.dumps({"query": "sam"}))
        data = json.loads(result)
        assert data[0]["Id"] == "003xx"
        sf.search_contacts.assert_called_once_with("sam")


@pytest.mark.asyncio
async def test_search_opportunities():
    sf = MagicMock()
    sf.search_open_opportunities.return_value = [{"Id": "006xx", "Name": "Deal"}]

    async with SessionLocal() as s:
        email = await _seed_email(s)
        ctx = ToolContext(sf=sf, session=s, email_id=email.id)
        result = await handle_tool_call(
            ctx, "search_open_opportunities", json.dumps({"account_id": "001xx"})
        )
        data = json.loads(result)
        assert data[0]["Id"] == "006xx"
        sf.search_open_opportunities.assert_called_once_with("001xx")


@pytest.mark.asyncio
async def test_propose_crm_update_writes_proposal_row():
    sf = MagicMock()
    async with SessionLocal() as s:
        email = await _seed_email(s)
        ctx = ToolContext(sf=sf, session=s, email_id=email.id)
        result = await handle_tool_call(
            ctx,
            "propose_crm_update",
            json.dumps(
                {
                    "sf_object_type": "Opportunity",
                    "sf_record_id": "006xx000000000001",
                    "before": {"StageName": "Discovery"},
                    "after": {"StageName": "Negotiation"},
                    "reasoning": "email says ready to negotiate",
                    "confidence": 0.9,
                }
            ),
        )
        ack = json.loads(result)
        assert ack["ok"] is True
        assert "proposal_id" in ack

        proposals = (await s.execute(select(Proposal))).scalars().all()
        assert len(proposals) == 1
        p = proposals[0]
        assert p.sf_object_type == "Opportunity"
        assert p.sf_record_id == "006xx000000000001"
        assert p.diff_payload == {
            "before": {"StageName": "Discovery"},
            "after": {"StageName": "Negotiation"},
        }
        assert p.confidence == 0.9
        assert p.status == ProposalStatus.pending


@pytest.mark.asyncio
async def test_propose_new_record_writes_with_no_record_id():
    sf = MagicMock()
    async with SessionLocal() as s:
        email = await _seed_email(s)
        ctx = ToolContext(sf=sf, session=s, email_id=email.id)
        await handle_tool_call(
            ctx,
            "propose_new_record",
            json.dumps(
                {
                    "sf_object_type": "Contact",
                    "fields": {
                        "FirstName": "Sam",
                        "LastName": "Patel",
                        "Email": "sam@acme.test",
                    },
                    "reasoning": "first-touch email from unknown sender",
                    "confidence": 0.85,
                }
            ),
        )
        p = (await s.execute(select(Proposal))).scalar_one()
        assert p.sf_record_id is None
        assert p.diff_payload["after"]["Email"] == "sam@acme.test"


@pytest.mark.asyncio
async def test_unknown_tool_raises():
    sf = MagicMock()
    async with SessionLocal() as s:
        email = await _seed_email(s)
        ctx = ToolContext(sf=sf, session=s, email_id=email.id)
        with pytest.raises(ValueError, match="unknown tool"):
            await handle_tool_call(ctx, "not_a_tool", "{}")
