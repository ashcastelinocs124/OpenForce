import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.config import get_settings
from openforce.db.models import Integration, IntegrationProvider


def authorize_url() -> str:
    s = get_settings()
    return (
        f"{s.sf_login_url}/services/oauth2/authorize"
        f"?response_type=code&client_id={s.sf_client_id}"
        f"&redirect_uri={s.sf_redirect_uri}&scope=api%20refresh_token%20offline_access"
    )


async def exchange_code(code: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"{s.sf_login_url}/services/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": s.sf_client_id,
                "client_secret": s.sf_client_secret,
                "redirect_uri": s.sf_redirect_uri,
            },
        )
        r.raise_for_status()
        return r.json()


async def save_sf_integration(session: AsyncSession, payload: dict) -> Integration:
    existing = (
        await session.execute(
            select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = Integration(provider=IntegrationProvider.salesforce, access_token="")
        session.add(existing)
    existing.access_token = payload["access_token"]
    existing.refresh_token = payload.get("refresh_token")
    existing.instance_url = payload.get("instance_url")
    existing.needs_reauth = False
    await session.commit()
    await session.refresh(existing)
    return existing


async def refresh_sf_tokens(session: AsyncSession, integration: Integration) -> Integration:
    s = get_settings()
    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"{s.sf_login_url}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": integration.refresh_token,
                "client_id": s.sf_client_id,
                "client_secret": s.sf_client_secret,
            },
        )
    if r.status_code != 200:
        integration.needs_reauth = True
        await session.commit()
        raise RuntimeError("SF refresh failed; needs_reauth set")
    payload = r.json()
    integration.access_token = payload["access_token"]
    await session.commit()
    return integration
