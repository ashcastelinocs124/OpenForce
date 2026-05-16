import json

from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.agent.prompts import SYSTEM_PROMPT
from openforce.agent.schemas import OPENAI_TOOLS
from openforce.agent.tools import ToolContext, handle_tool_call
from openforce.config import get_settings
from openforce.db.models import Email, EmailStatus
from openforce.salesforce.client import SalesforceClient

MAX_TOOL_ITERS = 6


def _format_user_msg(email: Email) -> str:
    return (
        f"From: {email.sender}\n"
        f"Subject: {email.subject}\n"
        f"Received: {email.received_at.isoformat()}\n\n"
        f"{email.body_text}"
    )


def _build_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


async def run_agent_for_email(
    session: AsyncSession,
    sf: SalesforceClient,
    email: Email,
    client_factory=_build_openai_client,
) -> EmailStatus:
    settings = get_settings()
    client = client_factory()
    ctx = ToolContext(sf=sf, session=session, email_id=email.id)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _format_user_msg(email)},
    ]

    proposed_anything = False

    for _ in range(MAX_TOOL_ITERS):
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        assistant_entry: dict = {"role": "assistant", "content": msg.content}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if not tool_calls:
            content = (msg.content or "").strip().lower()
            if proposed_anything:
                return EmailStatus.proposed
            return EmailStatus.irrelevant if "no_action" in content else EmailStatus.proposed

        for tc in tool_calls:
            try:
                result = await handle_tool_call(ctx, tc.function.name, tc.function.arguments)
                if tc.function.name in ("propose_crm_update", "propose_new_record"):
                    proposed_anything = True
            except Exception as e:  # noqa: BLE001 — surface to model as tool error
                result = json.dumps({"ok": False, "error": str(e)})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Iter budget exhausted without a final assistant turn.
    return EmailStatus.extraction_failed
