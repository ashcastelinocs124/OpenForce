"""End-to-end smoke test against a real Salesforce Developer Org.

Gated by env var OPENFORCE_RUN_E2E=1 because it hits a live SF org. Requires a
prior OAuth flow (Integration row with valid tokens) AND the seed_sf.py script
to have created the Acme demo data.

Run locally:
    OPENFORCE_RUN_E2E=1 uv run pytest tests/e2e/ -v
"""
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.config import get_settings
from openforce.db.models import (
    AuditLog,
    Email,
    EmailStatus,
    Integration,
    IntegrationProvider,
    Proposal,
    ProposalStatus,
)
from openforce.db.session import SessionLocal
from openforce.proposals.service import process_one_email
from openforce.salesforce.client import SalesforceClient
from openforce.salesforce.writer import execute_proposal

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENFORCE_RUN_E2E") != "1",
    reason="set OPENFORCE_RUN_E2E=1 to run the live-SF smoke test",
)


@pytest.mark.asyncio
async def test_end_to_end_stage_advance_against_dev_org():
    """Full path: seed email -> agent proposes -> approve -> verify SF Opportunity advanced.

    Resets the Opportunity stage back to Discovery afterwards.
    """
    settings = get_settings()
    eng = create_engine(settings.database_url_sync)

    # Resolve SF integration & Acme opportunity
    with Session(eng) as s:
        integration = s.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
        ).scalar_one()
    eng.dispose()

    sf = SalesforceClient(integration.access_token, integration.instance_url or "")
    opps = sf._sf.query("SELECT Id, StageName FROM Opportunity WHERE Name='Acme - Q3 Renewal'")["records"]
    assert opps, "run scripts/seed_sf.py first"
    opp_id = opps[0]["Id"]
    original_stage = opps[0]["StageName"]

    async with SessionLocal() as s:
        await s.execute(delete(AuditLog))
        await s.execute(delete(Proposal))
        await s.execute(delete(Email))

        email = Email(
            gmail_msg_id=f"e2e-{datetime.now(timezone.utc).isoformat()}",
            thread_id="t",
            sender="sam@acme.test",
            subject="Ready to sign",
            body_text="We're ready to move forward — please update the Q3 Renewal to Negotiation.",
            received_at=datetime.now(timezone.utc),
        )
        s.add(email)
        await s.commit()
        await s.refresh(email)

        new_status = await process_one_email(s, email.id)
        assert new_status == EmailStatus.proposed

        proposal = (
            await s.execute(select(Proposal).where(Proposal.email_id == email.id))
        ).scalar_one()
        assert proposal.sf_object_type == "Opportunity"
        assert proposal.sf_record_id == opp_id

        status = await execute_proposal(s, proposal.id)
        assert status == ProposalStatus.approved

    try:
        updated = sf.get_record("Opportunity", opp_id)
        assert updated["StageName"] != original_stage
    finally:
        # restore for next run
        sf.update_record("Opportunity", opp_id, {"StageName": original_stage})
