from __future__ import annotations

from datetime import date

import httpx
import pytest
from fake_carhauler import BASE, RATE_LIMITED

from mia.carhauler import CarHaulerClient, CarHaulerError, ErrorCode


async def test_catalog_lookups(client):
    makes = await client.makes()
    assert {"id": 23, "name": "Honda"} in makes
    assert {"id": 681, "name": "Civic"} in await client.models(23)
    assert 2025 in await client.years(681)
    trims = await client.trims(681, 2025)
    assert trims[0]["id"] == 34547


async def test_catalog_is_cached(client, fake_api):
    await client.makes()
    await client.makes()
    await client.models(23)
    await client.models(23)
    assert fake_api.calls["/car/makes"] == 1
    assert fake_api.calls["/car/models"] == 1


async def test_quote_by_trim(client):
    q = await client.quote("02110", "94103", trim_id=34547)
    assert q.price == 1291
    assert q.distance == 3095
    assert q.driving_time == "5 days and 2 hours drive"
    assert q.carrier == "open"


async def test_quote_sends_zip_with_leading_zero_and_options(client, fake_api):
    await client.quote(
        "2110", "94103", vehicle_type="suv", operational=False, shipping_date=date(2026, 12, 1)
    )
    request = fake_api.requests[-1]
    assert request.url.params["fromZip"] == "02110"
    assert request.url.params["vehicleType"] == "suv"
    assert request.url.params["isOperational"] == "false"
    assert request.url.params["shippingDate"] == "2026-12-01"


async def test_unknown_vehicle_type_is_rejected_locally(client, fake_api):
    with pytest.raises(CarHaulerError) as exc:
        await client.quote("02110", "94103", vehicle_type="spaceship")
    assert exc.value.code == ErrorCode.INVALID_VEHICLE_TYPE
    assert fake_api.calls["/quote"] == 0


@pytest.mark.parametrize(
    "from_zip, to_zip, trim, code",
    [
        ("00000", "94103", 34547, ErrorCode.INVALID_ORIGIN_ZIP),
        ("02110", "02110", 34547, ErrorCode.SAME_ZIP),
        ("02110", "94103", 999, ErrorCode.INVALID_TRIM),
    ],
)
async def test_quote_validation_errors_fail_fast(client, fake_api, from_zip, to_zip, trim, code):
    with pytest.raises(CarHaulerError) as exc:
        await client.quote(from_zip, to_zip, trim_id=trim)
    assert exc.value.code == code
    assert not exc.value.is_service_error
    assert fake_api.calls["/quote"] == 1  # not retried


async def test_rate_limit_is_retried(client, fake_api):
    fake_api.fail_next(RATE_LIMITED, RATE_LIMITED)
    q = await client.quote("02110", "94103", trim_id=34547)
    assert q.price == 1291
    assert fake_api.calls["/quote"] == 3


async def test_gives_up_after_three_attempts(client, fake_api):
    fake_api.fail_next(httpx.Response(503), httpx.ReadTimeout("slow"), httpx.Response(502))
    with pytest.raises(CarHaulerError) as exc:
        await client.quote("02110", "94103", trim_id=34547)
    assert exc.value.code == ErrorCode.UNAVAILABLE
    assert exc.value.is_service_error
    assert exc.value.attempts == 3
    assert fake_api.calls["/quote"] == 3


@pytest.mark.parametrize("status, code", [(401, ErrorCode.AUTH), (402, ErrorCode.PAYMENT_REQUIRED)])
async def test_auth_and_billing_errors_are_not_retried(client, fake_api, status, code):
    fake_api.fail_next(httpx.Response(status, json={"error": "nope"}))
    with pytest.raises(CarHaulerError) as exc:
        await client.makes()
    assert exc.value.code == code
    assert exc.value.is_service_error
    assert fake_api.calls["/car/makes"] == 1


async def test_failed_lookup_is_not_cached(client, fake_api):
    fake_api.fail_next(httpx.Response(402, json={}))
    with pytest.raises(CarHaulerError):
        await client.makes()
    assert await client.makes()  # next call goes through
    assert fake_api.calls["/car/makes"] == 2


async def test_wrong_key_maps_to_auth(fake_api):
    c = CarHaulerClient(api_key="wrong", base_url=BASE, retry_wait=0)
    with pytest.raises(CarHaulerError) as exc:
        await c.makes()
    assert exc.value.code == ErrorCode.AUTH
    await c.aclose()


async def test_missing_key(fake_api, monkeypatch):
    monkeypatch.delenv("CARHAULER_API_KEY", raising=False)
    monkeypatch.delenv("CARHAULER_API_KEY_QA", raising=False)
    c = CarHaulerClient(base_url=BASE, retry_wait=0)
    with pytest.raises(CarHaulerError) as exc:
        await c.makes()
    assert exc.value.code == ErrorCode.MISSING_API_KEY
    assert fake_api.calls["/car/makes"] == 0
    await c.aclose()
