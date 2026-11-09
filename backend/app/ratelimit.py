"""Fixed-window rate limits (same interface as fit-mgmt-app's app/ratelimit.py).

Stage 3 keeps the counters in memory: one API process locally (docker compose). Stage 4 moves
them to DynamoDB counters like fit, so the limits hold across Lambda instances; only
``_increment`` changes.
"""

import threading
import time

from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_counters: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)


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


def _increment(key: str, ttl_seconds: int) -> int:
    now = time.time()
    with _lock:
        for k in [k for k, (_, exp) in _counters.items() if exp <= now]:
            del _counters[k]
        n = _counters.get(key, (0, now + ttl_seconds))[0] + 1
        _counters[key] = (n, now + ttl_seconds)
        return n


def hit(name: str, window_seconds: int) -> int:
    """Record one event in the current window and return the window's total."""
    return _increment(_key(name, window_seconds), ttl_seconds=window_seconds * 2)


def reset() -> None:
    """Tests only."""
    with _lock:
        _counters.clear()


def too_many(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail)
