"""DynamoDB access (fit's pattern): one table, keys ``pk``/``sk``.

The agent worker writes the call records (``agent/src/mia/records.py`` documents the keys);
the API adds feedback, keeps the rate-limit counters (``COUNTER#...``, expired through the
``ttl`` attribute) and, from stage 6, reads calls for the dashboard.
"""

import os
import time
from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


def table_name() -> str:
    return os.environ.get("TABLE_NAME", "carhaul")


@lru_cache
def get_table():
    resource = boto3.resource(
        "dynamodb",
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT") or None,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    return resource.Table(table_name())


def create_table_if_missing() -> None:
    """Local dev and tests; on AWS Terraform creates the table."""
    client = get_table().meta.client
    if table_name() in client.list_tables()["TableNames"]:
        return
    client.create_table(
        TableName=table_name(),
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
    client.get_waiter("table_exists").wait(TableName=table_name())
    client.update_time_to_live(
        TableName=table_name(),
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )


def _from_dynamo(value: Any) -> Any:
    """Drop the keys and turn DynamoDB Decimals back into ints or floats."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items() if k not in ("pk", "sk", "ttl")}
    return value


def _to_dynamo(value: Any) -> Any:
    """DynamoDB rejects Python floats; store them as Decimals."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    return value


def put(pk: str, sk: str, data: dict[str, Any]) -> None:
    get_table().put_item(Item={**_to_dynamo(data), "pk": pk, "sk": sk})


def get(pk: str, sk: str) -> dict[str, Any] | None:
    row = get_table().get_item(Key={"pk": pk, "sk": sk}).get("Item")
    return _from_dynamo(row) if row else None


def query(pk: str, sk_prefix: str = "") -> list[dict[str, Any]]:
    condition = Key("pk").eq(pk)
    if sk_prefix:
        condition = condition & Key("sk").begins_with(sk_prefix)
    table = get_table()
    response = table.query(KeyConditionExpression=condition)
    rows = response["Items"]
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=condition, ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        rows.extend(response["Items"])
    return [_from_dynamo(r) for r in rows]


def latest(pk: str, limit: int) -> list[dict[str, Any]]:
    """The last ``limit`` rows under ``pk`` by sort key, newest first."""
    response = get_table().query(
        KeyConditionExpression=Key("pk").eq(pk), ScanIndexForward=False, Limit=limit
    )
    return [_from_dynamo(r) for r in response["Items"]]


def increment(key: str, ttl_seconds: int) -> int:
    """Atomically add 1 to a counter row and return the new value (rate limits)."""
    response = get_table().update_item(
        Key={"pk": f"COUNTER#{key}", "sk": "COUNTER"},
        UpdateExpression="ADD #n :one SET #ttl = if_not_exists(#ttl, :ttl)",
        ExpressionAttributeNames={"#n": "n", "#ttl": "ttl"},
        ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + ttl_seconds},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["n"])
