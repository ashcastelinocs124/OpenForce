import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.config import get_settings
from openforce.db.models import Integration, IntegrationProvider

_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def authorize_url() -> str:
    s = get_settings()
    return (
        f"{_AUTH_URL}"
        f"?response_type=code&client_id={s.google_client_id}"
        f"&redirect_uri={s.google_redirect_uri}"
        f"&scope={_GMAIL_SCOPE}"
        "&access_type=offline&prompt=consent"
    )


async def exchange_code(code: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        r = await http.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": s.google_redirect_uri,
            },
        )
        r.raise_for_status()
        return r.json()


async def save_gmail_integration(session: AsyncSession, payload: dict) -> Integration:
    existing = (
        await session.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.gmail)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = Integration(provider=IntegrationProvider.gmail, access_token="")
        session.add(existing)
    existing.access_token = payload["access_token"]
    if "refresh_token" in payload:
        existing.refresh_token = payload["refresh_token"]
    existing.needs_reauth = False
    await session.commit()
    await session.refresh(existing)
    return existing
