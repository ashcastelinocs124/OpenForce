import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass
class GmailMessage:
    msg_id: str
    thread_id: str
    sender: str
    subject: str
    body_text: str
    received_at: datetime


class GmailClient:
    def __init__(self, access_token: str, refresh_token: str | None) -> None:
        creds = Credentials(token=access_token, refresh_token=refresh_token)
        self._svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def list_history_since(self, history_id: str) -> tuple[list[str], str]:
        """Return (new_msg_ids, latest_history_id)."""
        resp = (
            self._svc.users()
            .history()
            .list(userId="me", startHistoryId=history_id, historyTypes=["messageAdded"])
            .execute()
        )
        msg_ids: list[str] = []
        for h in resp.get("history", []):
            for m in h.get("messagesAdded", []):
                msg_ids.append(m["message"]["id"])
        return msg_ids, resp.get("historyId", history_id)

    def initial_history_id(self) -> str:
        profile = self._svc.users().getProfile(userId="me").execute()
        return profile["historyId"]

    def get_message(self, msg_id: str) -> GmailMessage:
        m = self._svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in m["payload"]["headers"]}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        date_hdr = headers.get("date")
        received_at = parsedate_to_datetime(date_hdr) if date_hdr else datetime.now(timezone.utc)
        body = _extract_text(m["payload"])
        return GmailMessage(
            msg_id=m["id"],
            thread_id=m["threadId"],
            sender=sender,
            subject=subject,
            body_text=body,
            received_at=received_at,
        )


def _extract_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType", "").startswith("text/plain") and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_text(part)
        if text:
            return text
    return ""
