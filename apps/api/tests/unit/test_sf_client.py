from unittest.mock import MagicMock, patch

from openforce.salesforce.client import SalesforceClient


@patch("openforce.salesforce.client.Salesforce")
def test_search_contacts(SfMock):
    instance = SfMock.return_value
    instance.query.return_value = {
        "records": [
            {"Id": "003xx", "FirstName": "Sam", "LastName": "Patel", "Email": "sam@acme.test", "AccountId": "001xx"}
        ]
    }
    c = SalesforceClient(access_token="t", instance_url="https://x.my.salesforce.com")
    results = c.search_contacts("sam@acme.test")
    assert len(results) == 1
    assert results[0]["Id"] == "003xx"
    instance.query.assert_called_once()
    assert "sam@acme.test" in instance.query.call_args[0][0]


@patch("openforce.salesforce.client.Salesforce")
def test_search_open_opportunities(SfMock):
    instance = SfMock.return_value
    instance.query.return_value = {"records": [{"Id": "006xx", "Name": "Deal", "StageName": "Discovery"}]}
    c = SalesforceClient("t", "https://x")
    results = c.search_open_opportunities("001xx")
    assert results[0]["Id"] == "006xx"
    assert "001xx" in instance.query.call_args[0][0]
    assert "IsClosed=false" in instance.query.call_args[0][0]


@patch("openforce.salesforce.client.Salesforce")
def test_update_record_delegates_to_object_type(SfMock):
    instance = SfMock.return_value
    instance.Opportunity = MagicMock()
    c = SalesforceClient("t", "https://x")
    c.update_record("Opportunity", "006xx", {"StageName": "Negotiation"})
    instance.Opportunity.update.assert_called_once_with("006xx", {"StageName": "Negotiation"})


@patch("openforce.salesforce.client.Salesforce")
def test_create_record_returns_new_id(SfMock):
    instance = SfMock.return_value
    instance.Contact = MagicMock()
    instance.Contact.create.return_value = {"id": "003new", "success": True}
    c = SalesforceClient("t", "https://x")
    new_id = c.create_record("Contact", {"FirstName": "Sam", "LastName": "Patel"})
    assert new_id == "003new"


@patch("openforce.salesforce.client.Salesforce")
def test_get_record(SfMock):
    instance = SfMock.return_value
    instance.Opportunity = MagicMock()
    instance.Opportunity.get.return_value = {"Id": "006xx", "StageName": "Discovery", "Amount": 30000}
    c = SalesforceClient("t", "https://x")
    rec = c.get_record("Opportunity", "006xx")
    assert rec["StageName"] == "Discovery"
