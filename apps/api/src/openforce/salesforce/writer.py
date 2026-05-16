import uuid
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import (
    AuditLog,
    Integration,
    IntegrationProvider,
    Proposal,
    ProposalStatus,
)
from openforce.salesforce.client import SalesforceClient


def _default_sf_client(integration: Integration) -> SalesforceClient:
    return SalesforceClient(integration.access_token, integration.instance_url or "")


async def execute_proposal(
    session: AsyncSession,
    proposal_id: uuid.UUID,
    sf_client_factory: Callable[[Integration], SalesforceClient] = _default_sf_client,
) -> ProposalStatus:
    proposal = (
        await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    ).scalar_one()
    if proposal.status != ProposalStatus.pending:
        return proposal.status

    integration = (
        await session.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
        )
    ).scalar_one()
    sf = sf_client_factory(integration)

    audit_before: dict = {}
    audit_after: dict = {}
    audit_record_id: str
    try:
        if proposal.sf_record_id:
            claimed_before = proposal.diff_payload.get("before", {})
            current = sf.get_record(proposal.sf_object_type, proposal.sf_record_id)
            for field, claimed in claimed_before.items():
                if current.get(field) != claimed:
                    proposal.status = ProposalStatus.failed_validation
                    proposal.error = (
                        f"Field {field}: expected {claimed!r}, found {current.get(field)!r}"
                    )
                    await session.commit()
                    return proposal.status
            after = proposal.diff_payload["after"]
            sf.update_record(proposal.sf_object_type, proposal.sf_record_id, after)
            audit_before = {k: current.get(k) for k in after}
            audit_after = after
            audit_record_id = proposal.sf_record_id
        else:
            after = proposal.diff_payload.get("after", {})
            audit_record_id = sf.create_record(proposal.sf_object_type, after)
            audit_after = after
        proposal.status = ProposalStatus.approved
    except Exception as e:  # noqa: BLE001 — surface SF errors to dashboard
        proposal.status = ProposalStatus.failed
        proposal.error = str(e)
        await session.commit()
        return proposal.status

    session.add(
        AuditLog(
            proposal_id=proposal.id,
            sf_record_id=audit_record_id,
            before_state=audit_before,
            after_state=audit_after,
            success=True,
        )
    )
    await session.commit()
    return proposal.status
