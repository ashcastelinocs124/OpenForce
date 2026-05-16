from typing import Any, Literal

from pydantic import BaseModel, Field

SfObjectType = Literal["Account", "Contact", "Opportunity", "Task"]


class ProposeCrmUpdateArgs(BaseModel):
    sf_object_type: SfObjectType
    sf_record_id: str = Field(min_length=15, max_length=18)
    before: dict[str, Any]
    after: dict[str, Any]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProposeNewRecordArgs(BaseModel):
    sf_object_type: SfObjectType
    fields: dict[str, Any]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_salesforce_contacts",
            "description": "Search SF Contacts by name or email. Returns up to 10 candidates.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_open_opportunities",
            "description": "Return open Opportunities for a given AccountId.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_crm_update",
            "description": "Propose an update to an existing SF record. Provide before/after diff.",
            "parameters": ProposeCrmUpdateArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_new_record",
            "description": "Propose creating a new SF record.",
            "parameters": ProposeNewRecordArgs.model_json_schema(),
        },
    },
]
