import uuid
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.runner import run_agent_for_email
from openforce.db.models import Email, EmailStatus, Integration, IntegrationProvider
from openforce.salesforce.client import SalesforceClient


def _build_sf_client(integration: Integration) -> SalesforceClient:
    return SalesforceClient(integration.access_token, integration.instance_url or "")


async def process_one_email(
    session: AsyncSession,
    email_id: uuid.UUID,
    sf_client_factory: Callable[[Integration], SalesforceClient] = _build_sf_client,
    openai_client_factory=None,
) -> EmailStatus:
    email = (await session.execute(select(Email).where(Email.id == email_id))).scalar_one()
    integration = (
        await session.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
        )
    ).scalar_one()
    sf = sf_client_factory(integration)
    try:
        if openai_client_factory is not None:
            new_status = await run_agent_for_email(
                session, sf, email, client_factory=openai_client_factory
            )
        else:
            new_status = await run_agent_for_email(session, sf, email)
    except Exception as e:  # noqa: BLE001
        email.status = EmailStatus.extraction_failed
        email.error = str(e)
        await session.commit()
        return email.status
    email.status = new_status
    await session.commit()
    return new_status


async def process_unprocessed_batch(
    session: AsyncSession,
    limit: int = 20,
    sf_client_factory: Callable[[Integration], SalesforceClient] = _build_sf_client,
    openai_client_factory=None,
) -> int:
    rows = (
        await session.execute(
            select(Email.id).where(Email.status == EmailStatus.unprocessed).limit(limit)
        )
    ).scalars().all()
    for eid in rows:
        await process_one_email(
            session,
            eid,
            sf_client_factory=sf_client_factory,
            openai_client_factory=openai_client_factory,
        )
    return len(rows)
