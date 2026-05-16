from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.models import Email, EmailStatus, Integration, IntegrationProvider
from openforce.gmail.client import GmailClient


def _build_default_client(integration: Integration) -> GmailClient:
    return GmailClient(integration.access_token, integration.refresh_token)


async def ingest_new_emails(
    session: AsyncSession,
    client_factory=_build_default_client,
) -> int:
    integration = (
        await session.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.gmail)
        )
    ).scalar_one_or_none()
    if integration is None or integration.needs_reauth:
        return 0

    client = client_factory(integration)
    history_id = integration.history_id or client.initial_history_id()
    msg_ids, latest = client.list_history_since(history_id)

    inserted = 0
    for mid in msg_ids:
        msg = client.get_message(mid)
        email = Email(
            gmail_msg_id=msg.msg_id,
            thread_id=msg.thread_id,
            sender=msg.sender,
            subject=msg.subject,
            body_text=msg.body_text,
            received_at=msg.received_at,
            status=EmailStatus.unprocessed,
        )
        session.add(email)
        try:
            await session.commit()
            inserted += 1
        except IntegrityError:
            await session.rollback()  # duplicate gmail_msg_id

    integration.history_id = latest
    await session.commit()
    return inserted
