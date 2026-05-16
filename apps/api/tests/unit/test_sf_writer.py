from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
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
from openforce.db.session import SessionLocal
from openforce.salesforce.writer import execute_proposal


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(AuditLog))
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


async def _seed_proposal(session, *, sf_record_id, diff_payload) -> Proposal:
    email = Email(
        gmail_msg_id=f"m-{datetime.now(timezone.utc).isoformat()}",
        thread_id="t",
        sender="x",
        subject="y",
        body_text="",
        received_at=datetime.now(timezone.utc),
    )
    session.add(email)
    await session.commit()
    await session.refresh(email)

    p = Proposal(
        email_id=email.id,
        sf_object_type="Opportunity",
        sf_record_id=sf_record_id,
        diff_payload=diff_payload,
        reasoning="r",
        confidence=0.9,
        status=ProposalStatus.pending,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_writer_approves_when_before_state_matches():
    sf = MagicMock()
    sf.get_record.return_value = {"StageName": "Discovery", "Amount": 30000}

    async with SessionLocal() as s:
        p = await _seed_proposal(
            s,
            sf_record_id="006xx000000000001",
            diff_payload={
                "before": {"StageName": "Discovery"},
                "after": {"StageName": "Negotiation"},
            },
        )
        status = await execute_proposal(s, p.id, sf_client_factory=lambda _i: sf)
        assert status == ProposalStatus.approved
        sf.update_record.assert_called_once_with(
            "Opportunity", "006xx000000000001", {"StageName": "Negotiation"}
        )
        await s.refresh(p)
        assert p.status == ProposalStatus.approved

        audits = (await s.execute(select(AuditLog))).scalars().all()
        assert len(audits) == 1
        assert audits[0].sf_record_id == "006xx000000000001"
        assert audits[0].success is True


@pytest.mark.asyncio
async def test_writer_fails_validation_when_before_diverges():
    sf = MagicMock()
    sf.get_record.return_value = {"StageName": "Closed Won"}  # diverged

    async with SessionLocal() as s:
        p = await _seed_proposal(
            s,
            sf_record_id="006xx000000000002",
            diff_payload={
                "before": {"StageName": "Discovery"},
                "after": {"StageName": "Negotiation"},
            },
        )
        status = await execute_proposal(s, p.id, sf_client_factory=lambda _i: sf)
        assert status == ProposalStatus.failed_validation
        sf.update_record.assert_not_called()
        await s.refresh(p)
        assert "expected" in (p.error or "")


@pytest.mark.asyncio
async def test_writer_creates_new_record_when_no_record_id():
    sf = MagicMock()
    sf.create_record.return_value = "003newcontact"

    async with SessionLocal() as s:
        p = await _seed_proposal(
            s,
            sf_record_id=None,
            diff_payload={"before": {}, "after": {"FirstName": "Sam", "LastName": "Patel"}},
        )
        # override object type to Contact for this test
        p.sf_object_type = "Contact"
        await s.commit()

        status = await execute_proposal(s, p.id, sf_client_factory=lambda _i: sf)
        assert status == ProposalStatus.approved
        sf.create_record.assert_called_once()
        audit = (await s.execute(select(AuditLog))).scalar_one()
        assert audit.sf_record_id == "003newcontact"


@pytest.mark.asyncio
async def test_writer_marks_failed_on_sf_error():
    sf = MagicMock()
    sf.get_record.return_value = {"StageName": "Discovery"}
    sf.update_record.side_effect = RuntimeError("SF down")

    async with SessionLocal() as s:
        p = await _seed_proposal(
            s,
            sf_record_id="006xx000000000003",
            diff_payload={
                "before": {"StageName": "Discovery"},
                "after": {"StageName": "Negotiation"},
            },
        )
        status = await execute_proposal(s, p.id, sf_client_factory=lambda _i: sf)
        assert status == ProposalStatus.failed
        await s.refresh(p)
        assert p.error == "SF down"
