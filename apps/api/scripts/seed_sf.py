"""One-shot seed for SF Developer Org. Idempotent by name/email.

Requires an existing Salesforce integration row (run the OAuth flow first).

Usage: from apps/api/, run `uv run python scripts/seed_sf.py`.
"""
import asyncio

from sqlalchemy import select

from openforce.db.models import Integration, IntegrationProvider
from openforce.db.session import SessionLocal
from openforce.salesforce.client import SalesforceClient


async def _load_client() -> SalesforceClient:
    async with SessionLocal() as s:
        integration = (
            await s.execute(
                select(Integration).where(Integration.provider == IntegrationProvider.salesforce)
            )
        ).scalar_one()
    return SalesforceClient(integration.access_token, integration.instance_url or "")


async def main() -> None:
    c = await _load_client()

    accounts = c._sf.query("SELECT Id FROM Account WHERE Name='Acme Corp'")["records"]
    if accounts:
        account_id = accounts[0]["Id"]
        print(f"Account exists: {account_id}")
    else:
        account_id = c.create_record("Account", {"Name": "Acme Corp", "Industry": "Technology"})
        print(f"Account created: {account_id}")

    for first, last, email in [
        ("Sam", "Patel", "sam@acme.test"),
        ("Jordan", "Lee", "jordan@acme.test"),
    ]:
        existing = c._sf.query(f"SELECT Id FROM Contact WHERE Email='{email}'")["records"]
        if existing:
            print(f"Contact exists: {email}")
        else:
            cid = c.create_record(
                "Contact",
                {"FirstName": first, "LastName": last, "Email": email, "AccountId": account_id},
            )
            print(f"Contact created: {email} -> {cid}")

    opp_q = c._sf.query("SELECT Id FROM Opportunity WHERE Name='Acme - Q3 Renewal'")["records"]
    if opp_q:
        print(f"Opportunity exists: {opp_q[0]['Id']}")
    else:
        oid = c.create_record(
            "Opportunity",
            {
                "Name": "Acme - Q3 Renewal",
                "AccountId": account_id,
                "StageName": "Discovery",
                "Amount": 30000,
                "CloseDate": "2026-09-30",
            },
        )
        print(f"Opportunity created: {oid}")

    print("seed complete")


if __name__ == "__main__":
    asyncio.run(main())
