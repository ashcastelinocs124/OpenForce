import json
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.schemas import ProposeCrmUpdateArgs, ProposeNewRecordArgs
from openforce.db.models import Proposal, ProposalStatus
from openforce.salesforce.client import SalesforceClient


@dataclass
class ToolContext:
    sf: SalesforceClient
    session: AsyncSession
    email_id: uuid.UUID


async def handle_tool_call(ctx: ToolContext, name: str, raw_args: str) -> str:
    args = json.loads(raw_args)

    if name == "search_salesforce_contacts":
        return json.dumps(ctx.sf.search_contacts(args["query"]))

    if name == "search_open_opportunities":
        return json.dumps(ctx.sf.search_open_opportunities(args["account_id"]))

    if name == "propose_crm_update":
        parsed = ProposeCrmUpdateArgs(**args)
        proposal = Proposal(
            email_id=ctx.email_id,
            sf_object_type=parsed.sf_object_type,
            sf_record_id=parsed.sf_record_id,
            diff_payload={"before": parsed.before, "after": parsed.after},
            reasoning=parsed.reasoning,
            confidence=parsed.confidence,
            status=ProposalStatus.pending,
        )
        ctx.session.add(proposal)
        await ctx.session.commit()
        await ctx.session.refresh(proposal)
        return json.dumps({"ok": True, "proposal_id": str(proposal.id)})

    if name == "propose_new_record":
        parsed = ProposeNewRecordArgs(**args)
        proposal = Proposal(
            email_id=ctx.email_id,
            sf_object_type=parsed.sf_object_type,
            sf_record_id=None,
            diff_payload={"before": {}, "after": parsed.fields},
            reasoning=parsed.reasoning,
            confidence=parsed.confidence,
            status=ProposalStatus.pending,
        )
        ctx.session.add(proposal)
        await ctx.session.commit()
        await ctx.session.refresh(proposal)
        return json.dumps({"ok": True, "proposal_id": str(proposal.id)})

    raise ValueError(f"unknown tool: {name}")
