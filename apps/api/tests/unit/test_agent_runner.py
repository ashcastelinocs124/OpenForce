"""Tests for the agent runner — OpenAI function-calling loop.

We stub openai.OpenAI's chat.completions.create with a deterministic sequence of
responses simulating: search_salesforce_contacts -> propose_crm_update -> final
assistant turn.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from openforce.agent.runner import run_agent_for_email
from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus, Proposal
from openforce.db.session import SessionLocal


def _wipe() -> None:
    eng = create_engine(get_settings().database_url_sync)
    with Session(eng) as s:
        s.execute(delete(Proposal))
        s.execute(delete(Email))
        s.commit()
    eng.dispose()


def setup_function(_):
    _wipe()


def teardown_function(_):
    _wipe()


def _msg(content=None, tool_calls=None):
    """Mimic openai.ChatCompletionMessage shape."""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(name, args, tc_id="tc1"):
    return SimpleNamespace(
        id=tc_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _resp(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


async def _seed_email(session) -> Email:
    email = Email(
        gmail_msg_id=f"msg-{datetime.now(timezone.utc).isoformat()}",
        thread_id="t-1",
        sender="sam@acme.test",
        subject="Re: Q3 Renewal",
        body_text="ready to move forward",
        received_at=datetime.now(timezone.utc),
    )
    session.add(email)
    await session.commit()
    await session.refresh(email)
    return email


def _fake_openai_factory(responses):
    """Build a callable that returns a MagicMock OpenAI client returning the given responses in order."""
    def factory():
        client = MagicMock()
        client.chat.completions.create.side_effect = responses
        return client
    return factory


@pytest.mark.asyncio
async def test_runner_handles_search_then_propose_then_final():
    responses = [
        _resp(_msg(tool_calls=[_tool_call("search_salesforce_contacts", {"query": "sam"}, "t1")])),
        _resp(
            _msg(
                tool_calls=[
                    _tool_call(
                        "propose_crm_update",
                        {
                            "sf_object_type": "Opportunity",
                            "sf_record_id": "006xx000000000001",
                            "before": {"StageName": "Discovery"},
                            "after": {"StageName": "Negotiation"},
                            "reasoning": "email says ready",
                            "confidence": 0.9,
                        },
                        "t2",
                    )
                ]
            )
        ),
        _resp(_msg(content="done")),
    ]
    sf = MagicMock()
    sf.search_contacts.return_value = [{"Id": "003xx", "Email": "sam@acme.test"}]

    async with SessionLocal() as s:
        email = await _seed_email(s)
        status = await run_agent_for_email(
            s, sf, email, client_factory=_fake_openai_factory(responses)
        )
        assert status == EmailStatus.proposed

        proposals = (await s.execute(select(Proposal))).scalars().all()
        assert len(proposals) == 1
        assert proposals[0].sf_object_type == "Opportunity"
        assert proposals[0].confidence == 0.9


@pytest.mark.asyncio
async def test_runner_returns_irrelevant_on_no_action():
    responses = [_resp(_msg(content="no_action"))]
    sf = MagicMock()
    async with SessionLocal() as s:
        email = await _seed_email(s)
        status = await run_agent_for_email(
            s, sf, email, client_factory=_fake_openai_factory(responses)
        )
        assert status == EmailStatus.irrelevant
        assert (await s.execute(select(Proposal))).scalars().all() == []


@pytest.mark.asyncio
async def test_runner_returns_extraction_failed_when_budget_exhausted():
    # Always returns a tool call → never terminates.
    responses = [
        _resp(_msg(tool_calls=[_tool_call("search_salesforce_contacts", {"query": "x"}, "t1")]))
        for _ in range(20)
    ]
    sf = MagicMock()
    sf.search_contacts.return_value = []

    async with SessionLocal() as s:
        email = await _seed_email(s)
        status = await run_agent_for_email(
            s, sf, email, client_factory=_fake_openai_factory(responses)
        )
        assert status == EmailStatus.extraction_failed
