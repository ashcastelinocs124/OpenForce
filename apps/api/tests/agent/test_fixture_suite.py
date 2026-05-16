"""Fixture-driven agent regression suite.

These tests use a real OpenAI call by default (gated by OPENAI_API_KEY pointing at
a real key). For unit-test runs, they are skipped — the heavy lifting in CI is the
unit tests in tests/unit/. This suite doubles as the canned demo dataset.

Run locally with:
    OPENFORCE_RUN_AGENT_FIXTURES=1 OPENAI_API_KEY=sk-... uv run pytest tests/agent/ -v
"""
import json
import os
import pathlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.agent.runner import run_agent_for_email
from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus, Proposal
from openforce.db.session import SessionLocal
from openforce.salesforce.client import SalesforceClient

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "emails"
FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENFORCE_RUN_AGENT_FIXTURES") != "1",
    reason="set OPENFORCE_RUN_AGENT_FIXTURES=1 to run the live-OpenAI fixture suite",
)


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(Proposal))
        s.execute(delete(Email))
        s.commit()
    eng.dispose()


def _stub_sf_client(sf_state: dict) -> SalesforceClient:
    """Stub a SalesforceClient that returns canned data from the fixture's sf_state."""
    client = MagicMock(spec=SalesforceClient)
    contacts = sf_state.get("contacts", [])
    opportunities = sf_state.get("opportunities", [])

    def _search_contacts(query: str) -> list[dict]:
        q = query.lower()
        return [c for c in contacts if q in c.get("Email", "").lower() or q in (
            f"{c.get('FirstName', '')} {c.get('LastName', '')}".lower()
        )]

    def _search_opps(account_id: str) -> list[dict]:
        return [o for o in opportunities if o.get("AccountId") == account_id]

    client.search_contacts.side_effect = _search_contacts
    client.search_open_opportunities.side_effect = _search_opps
    return client


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
@pytest.mark.asyncio
async def test_fixture(path: pathlib.Path):
    fixture = json.loads(path.read_text())
    _wipe()

    async with SessionLocal() as s:
        email = Email(
            gmail_msg_id=f"fixture-{fixture['name']}",
            thread_id="t",
            sender=fixture["email"]["sender"],
            subject=fixture["email"]["subject"],
            body_text=fixture["email"]["body_text"],
            received_at=datetime.fromisoformat(
                fixture["email"]["received_at"].replace("Z", "+00:00")
            ),
        )
        s.add(email)
        await s.commit()
        await s.refresh(email)

        sf = _stub_sf_client(fixture["sf_state"])
        status = await run_agent_for_email(s, sf, email)

        expect = fixture["expect"]
        if "email_status" in expect:
            assert status == EmailStatus(expect["email_status"]), (
                f"{fixture['name']}: expected {expect['email_status']}, got {status}"
            )

        proposals = (await s.execute(select(Proposal).where(Proposal.email_id == email.id))).scalars().all()

        if "proposals_count" in expect:
            assert len(proposals) == expect["proposals_count"]
        if "proposals_count_min" in expect:
            assert len(proposals) >= expect["proposals_count_min"]

        if "max_confidence" in expect and proposals:
            assert max(p.confidence for p in proposals) <= expect["max_confidence"]

        if "reasoning_must_mention" in expect:
            joined = " ".join(p.reasoning.lower() for p in proposals)
            for needle in expect["reasoning_must_mention"]:
                assert needle.lower() in joined, f"{fixture['name']}: reasoning missing {needle!r}"

        proposal_expect = expect.get("proposal")
        if proposal_expect and proposals:
            p = proposals[0]
            if "sf_object_type" in proposal_expect:
                assert p.sf_object_type == proposal_expect["sf_object_type"]
            if "sf_record_id" in proposal_expect:
                assert p.sf_record_id == proposal_expect["sf_record_id"]
            if "after_contains_keys" in proposal_expect:
                after_keys = set(p.diff_payload.get("after", {}).keys())
                assert set(proposal_expect["after_contains_keys"]).issubset(after_keys)
            if "min_confidence" in proposal_expect:
                assert p.confidence >= proposal_expect["min_confidence"]
