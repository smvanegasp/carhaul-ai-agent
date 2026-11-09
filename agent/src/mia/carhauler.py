"""Async client for the CarHauler247 public API v2 (quotes and the vehicle catalog).

Docs: https://carhauler247.com/api-docs/v2 (OpenAPI: /openapi/v2.json). Behavior observed on
2026-11-08 that the docs don't spell out:

- Quote failures come back as HTTP 200 with ``{"success": false, "message": ...}``.
- ``/quote`` has a short burst limit even though v2 says "no rate limit": after a handful of
  quotes in a few seconds it answers ``success:false`` "Too many requests...", clearing in ~15 s.
- An unknown ``vehicleType`` is silently priced as a sedan, so we validate types ourselves.
- ``fromZip``/``toZip`` are integers in the spec; send them as 5-character strings to keep the
  leading zero (Boston is 02110).

Retries: at most 3 attempts with exponential backoff, only for transient failures (network,
timeouts, 5xx, rate limit). Anything else fails fast with a typed ``CarHaulerError`` so the agent
can tell the caller what to fix, or escalate.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_BASE_URL = "https://carhauler247.com/api/public/v2"
CATALOG_TTL_SECONDS = 24 * 3600

# Values the API prices differently; anything else would silently become a sedan.
VEHICLE_TYPES = (
    "sedan",
    "suv",
    "pickup",
    "truck",
    "van",
    "minivan",
    "hatchback",
    "convertible",
    "coupe",
    "wagon",
)


class ErrorCode(StrEnum):
    AUTH = "AUTH"  # 401: missing, invalid or revoked key
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"  # 402: free call allowance used up
    RATE_LIMITED = "RATE_LIMITED"  # "Too many requests" (retried first)
    UNAVAILABLE = "UNAVAILABLE"  # network error, timeout or 5xx (retried first)
    INVALID_ORIGIN_ZIP = "INVALID_ORIGIN_ZIP"
    INVALID_DESTINATION_ZIP = "INVALID_DESTINATION_ZIP"
    SAME_ZIP = "SAME_ZIP"
    INVALID_TRIM = "INVALID_TRIM"
    INVALID_DATE = "INVALID_DATE"
    INVALID_VEHICLE_TYPE = "INVALID_VEHICLE_TYPE"
    QUOTE_FAILED = "QUOTE_FAILED"  # any other success:false
    BAD_RESPONSE = "BAD_RESPONSE"  # unexpected status or body
    MISSING_API_KEY = "MISSING_API_KEY"


# Failures that mean "the service, not the caller's details, is the problem": escalate.
SERVICE_ERRORS = frozenset(
    {
        ErrorCode.AUTH,
        ErrorCode.PAYMENT_REQUIRED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.UNAVAILABLE,
        ErrorCode.BAD_RESPONSE,
        ErrorCode.MISSING_API_KEY,
        ErrorCode.QUOTE_FAILED,
    }
)

_RETRYABLE = frozenset({ErrorCode.RATE_LIMITED, ErrorCode.UNAVAILABLE})


class CarHaulerError(Exception):
    def __init__(self, code: ErrorCode, message: str = "", attempts: int = 1):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message
        self.attempts = attempts

    @property
    def is_service_error(self) -> bool:
        return self.code in SERVICE_ERRORS


@dataclass(frozen=True)
class Quote:
    price: int
    distance: int  # miles
    driving_time: str  # e.g. "5 days and 2 hours drive"
    vehicle_type: str
    operational: bool
    carrier: str = "open"


def _classify_quote_failure(message: str) -> ErrorCode:
    m = message.lower()
    if "too many requests" in m:
        return ErrorCode.RATE_LIMITED
    if "cannot be the same" in m:  # "Origin and destination ZIP codes cannot be the same"
        return ErrorCode.SAME_ZIP
    if "origin zip" in m:
        return ErrorCode.INVALID_ORIGIN_ZIP
    if "destination zip" in m:
        return ErrorCode.INVALID_DESTINATION_ZIP
    if "trim" in m:
        return ErrorCode.INVALID_TRIM
    if "date" in m:
        return ErrorCode.INVALID_DATE
    return ErrorCode.QUOTE_FAILED


def _api_key_from_env() -> str | None:
    return os.environ.get("CARHAULER_API_KEY") or os.environ.get("CARHAULER_API_KEY_QA") or None


class CarHaulerClient:
    """One per worker process: the catalog cache is shared by every call it serves."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        timeout: float = 8.0,
        max_attempts: int = 3,
        retry_wait: float = 2.0,
        http: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key if api_key is not None else _api_key_from_env()
        self._base_url = base_url or os.environ.get("CARHAULER_BASE_URL") or DEFAULT_BASE_URL
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._max_attempts = max_attempts
        self._retry_wait = retry_wait  # backoff multiplier in seconds: waits 2 s, then 4 s
        self._cache: dict[tuple[str, tuple[tuple[str, Any], ...]], tuple[float, Any]] = {}
        self._inflight: dict[tuple[str, tuple[tuple[str, Any], ...]], asyncio.Future] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- transport -------------------------------------------------------------------------

    async def _get_once(self, path: str, params: dict[str, Any]) -> Any:
        if not self._api_key:
            raise CarHaulerError(ErrorCode.MISSING_API_KEY, "CARHAULER_API_KEY is not set")
        try:
            resp = await self._http.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise CarHaulerError(ErrorCode.UNAVAILABLE, f"timeout: {exc}") from exc
        except httpx.TransportError as exc:
            raise CarHaulerError(ErrorCode.UNAVAILABLE, f"network: {exc}") from exc

        if resp.status_code == 401:
            raise CarHaulerError(ErrorCode.AUTH, resp.text[:200])
        if resp.status_code == 402:
            raise CarHaulerError(ErrorCode.PAYMENT_REQUIRED, resp.text[:200])
        if resp.status_code == 429:
            raise CarHaulerError(ErrorCode.RATE_LIMITED, resp.text[:200])
        if resp.status_code >= 500:
            raise CarHaulerError(ErrorCode.UNAVAILABLE, f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise CarHaulerError(ErrorCode.BAD_RESPONSE, f"HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise CarHaulerError(ErrorCode.BAD_RESPONSE, "response is not JSON") from exc
        if isinstance(body, dict) and body.get("success") is False:
            message = str(body.get("message") or "")
            raise CarHaulerError(_classify_quote_failure(message), message)
        return body

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        attempt = 0
        try:
            async for attempt_state in AsyncRetrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential(multiplier=self._retry_wait, max=8),
                retry=retry_if_exception(
                    lambda e: isinstance(e, CarHaulerError) and e.code in _RETRYABLE
                ),
                reraise=True,
            ):
                with attempt_state:
                    attempt = attempt_state.retry_state.attempt_number
                    return await self._get_once(path, params)
        except CarHaulerError as exc:
            exc.attempts = attempt
            raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def _get_cached(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Catalog lookups barely change: cache them for a day, and let concurrent callers
        share one request instead of each spending a call."""
        key = (path, tuple(sorted((params or {}).items())))
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        if key in self._inflight:
            return await asyncio.shield(self._inflight[key])
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await self._get(path, params)
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved: other waiters may not exist
            raise
        else:
            self._cache[key] = (time.monotonic() + CATALOG_TTL_SECONDS, data)
            future.set_result(data)
            return data
        finally:
            del self._inflight[key]

    # --- catalog ---------------------------------------------------------------------------

    async def makes(self) -> list[dict[str, Any]]:
        return await self._get_cached("/car/makes")

    async def models(self, make_id: int) -> list[dict[str, Any]]:
        return await self._get_cached("/car/models", {"makeId": make_id})

    async def years(self, model_id: int) -> list[int]:
        return await self._get_cached("/car/years", {"modelId": model_id})

    async def trims(self, model_id: int, year: int) -> list[dict[str, Any]]:
        return await self._get_cached("/car/trims", {"modelId": model_id, "year": year})

    # --- quote -----------------------------------------------------------------------------

    async def quote(
        self,
        from_zip: str,
        to_zip: str,
        *,
        trim_id: int | None = None,
        vehicle_type: str | None = None,
        operational: bool = True,
        shipping_date: date | None = None,
    ) -> Quote:
        params: dict[str, Any] = {
            "fromZip": str(from_zip).zfill(5),
            "toZip": str(to_zip).zfill(5),
            "isOperational": "true" if operational else "false",
        }
        if trim_id is not None:
            params["trimId"] = trim_id
        elif vehicle_type is not None:
            if vehicle_type not in VEHICLE_TYPES:
                raise CarHaulerError(ErrorCode.INVALID_VEHICLE_TYPE, vehicle_type)
            params["vehicleType"] = vehicle_type
        if shipping_date is not None:
            params["shippingDate"] = shipping_date.isoformat()

        body = await self._get("/quote", params)
        try:
            q = body["quote"]
            return Quote(
                price=int(q["price"]),
                distance=int(q["distance"]),
                driving_time=str(q["drivingTime"]),
                vehicle_type=str(q.get("vehicleType") or vehicle_type or "sedan"),
                operational=bool(q.get("operational", operational)),
                carrier=str(q.get("carrier") or "open"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CarHaulerError(ErrorCode.BAD_RESPONSE, f"unexpected quote body: {body}") from exc
