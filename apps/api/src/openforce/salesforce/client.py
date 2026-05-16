from typing import Any

from simple_salesforce import Salesforce


class SalesforceClient:
    """Thin wrapper around simple-salesforce for read + write operations the agent needs."""

    def __init__(self, access_token: str, instance_url: str) -> None:
        self._sf = Salesforce(instance_url=instance_url, session_id=access_token)

    def search_contacts(self, query: str) -> list[dict[str, Any]]:
        q = query.replace("'", "\\'")
        soql = (
            "SELECT Id, FirstName, LastName, Email, AccountId "
            f"FROM Contact WHERE Email LIKE '%{q}%' OR Name LIKE '%{q}%' LIMIT 10"
        )
        res = self._sf.query(soql)
        return res["records"]

    def search_open_opportunities(self, account_id: str) -> list[dict[str, Any]]:
        soql = (
            "SELECT Id, Name, StageName, Amount, CloseDate "
            f"FROM Opportunity WHERE AccountId='{account_id}' AND IsClosed=false LIMIT 25"
        )
        return self._sf.query(soql)["records"]

    def get_record(self, object_type: str, record_id: str) -> dict[str, Any]:
        return getattr(self._sf, object_type).get(record_id)

    def update_record(self, object_type: str, record_id: str, fields: dict[str, Any]) -> None:
        getattr(self._sf, object_type).update(record_id, fields)

    def create_record(self, object_type: str, fields: dict[str, Any]) -> str:
        res = getattr(self._sf, object_type).create(fields)
        return res["id"]
