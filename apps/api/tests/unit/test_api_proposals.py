from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import (
    AuditLog,
    Email,
    Integration,
    IntegrationProvider,
    Proposal,
    ProposalStatus,
)
from openforce.main import app


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(AuditLog))
        s.execute(delete(Proposal))
        s.execute(delete(Email))
        s.execute(delete(Integration))
        s.commit()
    eng.dispose()


def _seed_pending_proposal(*, sf_record_id: str | None = "006xx000000000001") -> dict:
    """Returns dict with seeded IDs."""
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        e = Email(
            gmail_msg_id=f"m-{datetime.now(timezone.utc).isoformat()}",
            thread_id="t",
            sender="x",
            subject="y",
            body_text="",
            received_at=datetime.now(timezone.utc),
        )
        s.add(e)
        s.commit()
        s.refresh(e)
        p = Proposal(
            email_id=e.id,
            sf_object_type="Opportunity",
            sf_record_id=sf_record_id,
            diff_payload={"before": {"StageName": "Discovery"}, "after": {"StageName": "Negotiation"}},
            reasoning="r",
            confidence=0.8,
            status=ProposalStatus.pending,
        )
        s.add(p)
        s.add(
            Integration(
                provider=IntegrationProvider.salesforce,
                access_token="t",
                instance_url="https://x.my.salesforce.com",
            )
        )
        s.commit()
        s.refresh(p)
        return {"email_id": str(e.id), "proposal_id": str(p.id)}


def setup_function(_):
    _wipe()


def teardown_function(_):
    _wipe()


@pytest.mark.asyncio
async def test_list_proposals_filters_by_status():
    seeded = _seed_pending_proposal()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/proposals?status=pending")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == seeded["proposal_id"]
        assert data[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_proposal_by_id():
    seeded = _seed_pending_proposal()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/proposals/{seeded['proposal_id']}")
        assert r.status_code == 200
        assert r.json()["id"] == seeded["proposal_id"]


@pytest.mark.asyncio
async def test_get_proposal_404():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/proposals/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_edit_proposal_updates_after_payload():
    seeded = _seed_pending_proposal()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            f"/proposals/{seeded['proposal_id']}",
            json={"after": {"StageName": "Closed Won", "Amount": 45000}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["diff_payload"]["after"]["StageName"] == "Closed Won"
        assert body["diff_payload"]["after"]["Amount"] == 45000


@pytest.mark.asyncio
async def test_reject_flips_status():
    seeded = _seed_pending_proposal()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(f"/proposals/{seeded['proposal_id']}/reject")
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_approve_invokes_writer():
    seeded = _seed_pending_proposal()
    transport = httpx.ASGITransport(app=app)

    # Patch SalesforceClient construction inside writer to return a controlled mock.
    with patch("openforce.salesforce.writer.SalesforceClient") as SfCtor:
        sf_mock = SfCtor.return_value
        sf_mock.get_record.return_value = {"StageName": "Discovery"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"/proposals/{seeded['proposal_id']}/approve")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "approved"
            sf_mock.update_record.assert_called_once()
