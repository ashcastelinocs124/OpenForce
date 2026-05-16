from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import Proposal, ProposalStatus
from openforce.db.session import get_session
from openforce.salesforce.writer import execute_proposal

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_id: UUID
    sf_object_type: str
    sf_record_id: str | None
    diff_payload: dict[str, Any]
    reasoning: str
    confidence: float
    status: ProposalStatus
    error: str | None


class EditIn(BaseModel):
    after: dict[str, Any]


@router.get("", response_model=list[ProposalOut])
async def list_proposals(
    status: ProposalStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Proposal]:
    stmt = select(Proposal).order_by(Proposal.confidence.asc(), Proposal.created_at.desc())
    if status:
        stmt = stmt.where(Proposal.status == status)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{proposal_id}", response_model=ProposalOut)
async def get_proposal(
    proposal_id: UUID, session: AsyncSession = Depends(get_session)
) -> Proposal:
    p = (
        await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404)
    return p


@router.patch("/{proposal_id}", response_model=ProposalOut)
async def edit_proposal(
    proposal_id: UUID,
    body: EditIn,
    session: AsyncSession = Depends(get_session),
) -> Proposal:
    p = (
        await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404)
    if p.status != ProposalStatus.pending:
        raise HTTPException(status_code=400, detail="only pending proposals can be edited")
    p.diff_payload = {**p.diff_payload, "after": body.after}
    await session.commit()
    await session.refresh(p)
    return p


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
async def approve(
    proposal_id: UUID, session: AsyncSession = Depends(get_session)
) -> Proposal:
    await execute_proposal(session, proposal_id)
    return (
        await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    ).scalar_one()


@router.post("/{proposal_id}/reject", response_model=ProposalOut)
async def reject(
    proposal_id: UUID, session: AsyncSession = Depends(get_session)
) -> Proposal:
    p = (
        await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404)
    p.status = ProposalStatus.rejected
    await session.commit()
    await session.refresh(p)
    return p
