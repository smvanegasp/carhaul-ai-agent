from __future__ import annotations

import pytest
import respx
from fake_carhauler import BASE, FakeCarHauler

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
