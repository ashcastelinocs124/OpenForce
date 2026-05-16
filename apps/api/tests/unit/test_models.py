import uuid
from datetime import datetime, timezone

import pytest

from openforce.db.models import Email, EmailStatus
from openforce.db.session import SessionLocal


@pytest.mark.asyncio
async def test_email_insert_and_select():
    async with SessionLocal() as s:
        e = Email(
            gmail_msg_id=f"msg-{uuid.uuid4()}",
            thread_id="t-1",
            sender="sam@acme.test",
            subject="Re: contract",
            body_text="ping",
            received_at=datetime.now(timezone.utc),
        )
        s.add(e)
        await s.commit()
        await s.refresh(e)
        assert e.status == EmailStatus.unprocessed
        assert e.id is not None
