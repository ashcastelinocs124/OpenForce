import base64
from datetime import datetime
from unittest.mock import MagicMock, patch

from openforce.gmail.client import GmailClient, _extract_text


def _mock_build_chain(*, history_resp=None, profile_resp=None, message_resp=None):
    """Build a MagicMock that mimics the googleapiclient builder chain."""
    svc = MagicMock()
    users = svc.users.return_value
    if history_resp is not None:
        users.history.return_value.list.return_value.execute.return_value = history_resp
    if profile_resp is not None:
        users.getProfile.return_value.execute.return_value = profile_resp
    if message_resp is not None:
        users.messages.return_value.get.return_value.execute.return_value = message_resp
    return svc


@patch("openforce.gmail.client.build")
@patch("openforce.gmail.client.Credentials")
def test_list_history_since_extracts_message_ids(creds_mock, build_mock):
    build_mock.return_value = _mock_build_chain(
        history_resp={
            "history": [
                {"messagesAdded": [{"message": {"id": "m1"}}, {"message": {"id": "m2"}}]},
                {"messagesAdded": [{"message": {"id": "m3"}}]},
            ],
            "historyId": "12345",
        }
    )
    c = GmailClient("token", "refresh")
    ids, latest = c.list_history_since("100")
    assert ids == ["m1", "m2", "m3"]
    assert latest == "12345"


@patch("openforce.gmail.client.build")
@patch("openforce.gmail.client.Credentials")
def test_initial_history_id(creds_mock, build_mock):
    build_mock.return_value = _mock_build_chain(profile_resp={"historyId": "999"})
    c = GmailClient("token", None)
    assert c.initial_history_id() == "999"


@patch("openforce.gmail.client.build")
@patch("openforce.gmail.client.Credentials")
def test_get_message_parses_headers_and_body(creds_mock, build_mock):
    body_text = "Hello\nFollow up please."
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
    build_mock.return_value = _mock_build_chain(
        message_resp={
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "sam@acme.test"},
                    {"name": "Subject", "value": "Re: Q3"},
                    {"name": "Date", "value": "Mon, 10 May 2026 10:00:00 +0000"},
                ],
                "body": {"data": encoded},
            },
        }
    )
    c = GmailClient("token", None)
    msg = c.get_message("m1")
    assert msg.msg_id == "m1"
    assert msg.thread_id == "t1"
    assert msg.sender == "sam@acme.test"
    assert msg.subject == "Re: Q3"
    assert msg.body_text == body_text
    assert isinstance(msg.received_at, datetime)


def test_extract_text_walks_multipart():
    body_text = "the body"
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": "ignored"}},
            {"mimeType": "text/plain", "body": {"data": encoded}},
        ],
    }
    assert _extract_text(payload) == body_text


def test_extract_text_returns_empty_when_no_plain_text():
    assert _extract_text({"mimeType": "image/png", "body": {}}) == ""
