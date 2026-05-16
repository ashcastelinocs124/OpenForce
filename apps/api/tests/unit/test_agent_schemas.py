import pytest
from pydantic import ValidationError

from openforce.agent.schemas import (
    OPENAI_TOOLS,
    ProposeCrmUpdateArgs,
    ProposeNewRecordArgs,
)


def test_rejects_short_record_id():
    with pytest.raises(ValidationError):
        ProposeCrmUpdateArgs(
            sf_object_type="Opportunity",
            sf_record_id="too-short",
            before={"StageName": "Discovery"},
            after={"StageName": "Negotiation"},
            reasoning="...",
            confidence=0.8,
        )


def test_rejects_too_long_record_id():
    with pytest.raises(ValidationError):
        ProposeCrmUpdateArgs(
            sf_object_type="Opportunity",
            sf_record_id="0" * 19,
            before={},
            after={},
            reasoning="x",
            confidence=0.5,
        )


def test_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        ProposeCrmUpdateArgs(
            sf_object_type="Opportunity",
            sf_record_id="006xx000000000000",
            before={},
            after={},
            reasoning="...",
            confidence=1.5,
        )


def test_rejects_invalid_object_type():
    with pytest.raises(ValidationError):
        ProposeCrmUpdateArgs(
            sf_object_type="Lead",  # not in the Literal
            sf_record_id="006xx000000000000",
            before={},
            after={},
            reasoning="x",
            confidence=0.5,
        )


def test_propose_new_record_accepts_valid():
    args = ProposeNewRecordArgs(
        sf_object_type="Contact",
        fields={"FirstName": "Sam", "LastName": "Patel", "Email": "sam@acme.test"},
        reasoning="First-touch email from unknown sender",
        confidence=0.85,
    )
    assert args.fields["Email"] == "sam@acme.test"


def test_openai_tools_has_four_function_tools():
    assert len(OPENAI_TOOLS) == 4
    names = {t["function"]["name"] for t in OPENAI_TOOLS}
    assert names == {
        "search_salesforce_contacts",
        "search_open_opportunities",
        "propose_crm_update",
        "propose_new_record",
    }
    for t in OPENAI_TOOLS:
        assert t["type"] == "function"
        assert "description" in t["function"]
        assert "parameters" in t["function"]
