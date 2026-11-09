from __future__ import annotations

import boto3
import pytest
import respx
from fake_carhauler import BASE, FakeCarHauler
from moto import mock_aws

from mia.carhauler import CarHaulerClient
from mia.vehicles import VehicleResolver


@pytest.fixture
def fake_api():
    fake = FakeCarHauler()
    with respx.mock(assert_all_called=False) as router:
        router.route(url__startswith=BASE).mock(side_effect=fake.handler)
        yield fake


@pytest.fixture
async def client(fake_api):
    # retry_wait=0: retries happen instantly in tests.
    c = CarHaulerClient(api_key="test-key", base_url=BASE, retry_wait=0)
    yield c
    await c.aclose()


@pytest.fixture
def resolver(client):
    return VehicleResolver(client)


@pytest.fixture
def table(monkeypatch):
    """An empty DynamoDB table (moto) that records.py and catalog.py write to."""
    monkeypatch.setenv("TABLE_NAME", "carhaul-test")
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    for name, value in (("AWS_ACCESS_KEY_ID", "test"), ("AWS_SECRET_ACCESS_KEY", "test")):
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    from mia import records

    with mock_aws():
        records._table.cache_clear()
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName="carhaul-test",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield boto3.resource("dynamodb", region_name="us-east-1").Table("carhaul-test")
    records._table.cache_clear()
