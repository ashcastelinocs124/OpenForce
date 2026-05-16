from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openforce.db.session import get_session
from openforce.salesforce.oauth import (
    authorize_url as sf_authorize_url,
)
from openforce.salesforce.oauth import (
    exchange_code as sf_exchange_code,
)
from openforce.salesforce.oauth import (
    save_sf_integration,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/salesforce/start")
async def sf_start() -> dict[str, str]:
    return {"url": sf_authorize_url()}


@router.get("/salesforce/callback")
async def sf_callback(
    code: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    payload = await sf_exchange_code(code)
    await save_sf_integration(session, payload)
    return {"status": "connected"}
