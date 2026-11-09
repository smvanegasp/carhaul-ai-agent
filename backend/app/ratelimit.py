"""Fixed-window rate limits backed by DynamoDB counters (fit's app/ratelimit.py), so the limits
hold across Lambda instances. DynamoDB deletes old windows through the ``ttl`` attribute."""

import time

from fastapi import HTTPException, Request, status

from app import db


def client_ip(request: Request) -> str:
    # Behind CloudFront the viewer's address arrives in this header ("ip:port").
    viewer = request.headers.get("cloudfront-viewer-address")
    if viewer:
        return viewer.rsplit(":", 1)[0]
    # Through ngrok (local sharing) the proxy appends the viewer's address to X-Forwarded-For;
    # take the last entry, since earlier ones are whatever the client sent.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


def _key(name: str, window_seconds: int) -> str:
    return f"{name}#{int(time.time()) // window_seconds}"


def hit(name: str, window_seconds: int) -> int:
    """Record one event in the current window and return the window's total."""
    return db.increment(_key(name, window_seconds), ttl_seconds=window_seconds * 2)


def too_many(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail)
