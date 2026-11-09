import os

import pytest
from moto import mock_aws

from app import db, ratelimit


@pytest.fixture(autouse=True)
def aws():
    """Every test gets a fresh in-memory DynamoDB table (moto) and fresh rate-limit counters."""
    os.environ.update(
        AWS_ACCESS_KEY_ID="test",
        AWS_SECRET_ACCESS_KEY="test",
        AWS_REGION="us-east-1",
        TABLE_NAME="carhaul-test",
    )
    for name in ("DYNAMODB_ENDPOINT", "AUTO_CREATE_TABLE", "AWS_PROFILE"):
        os.environ.pop(name, None)
    ratelimit.reset()
    with mock_aws():
        db.get_table.cache_clear()
        db.create_table_if_missing()
        yield
    db.get_table.cache_clear()
    ratelimit.reset()
