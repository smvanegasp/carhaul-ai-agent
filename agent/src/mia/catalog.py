"""The CarHauler catalog snapshot the voice worker starts with, kept on disk.

The vehicle resolver needs the catalog (makes, models per make) and the (make, model) index for
callers who name only the model. Building it takes 69 CarHauler calls (~1 s). **Catalog calls
count toward the API's allowance**: on 2026-11-09 the free tier (1,000 calls) ran out after a
day of tests that restarted the worker many times, each start re-fetching the catalog. So the
snapshot is saved to a file and reused across restarts for a week (makes and models barely
change); only a missing or stale file triggers a fetch.

Each call still gets its own client (an httpx client belongs to one event loop), seeded with
this snapshot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from mia.carhauler import CarHaulerClient
from mia.vehicles import VehicleResolver

logger = logging.getLogger("mia.catalog")

MAX_AGE_SECONDS = 7 * 24 * 3600
DEFAULT_FILE = Path.home() / ".cache" / "mia" / "catalog.json"

Snapshot = dict[str, Any]  # {"cache": client cache entries, "index": model index or None}
EMPTY: Snapshot = {"cache": {}, "index": None}


def cache_file() -> Path:
    return Path(os.environ.get("MIA_CATALOG_FILE") or DEFAULT_FILE)


def save(path: Path, snapshot: Snapshot, now: float | None = None) -> None:
    entries = [
        {"path": key[0], "params": [list(p) for p in key[1]], "data": data}
        for key, (_expires, data) in snapshot["cache"].items()
    ]
    body = {"saved_at": time.time() if now is None else now, "entries": entries}
    body["index"] = snapshot["index"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves half a file


def load(path: Path, max_age: float = MAX_AGE_SECONDS, now: float | None = None) -> Snapshot | None:
    """The saved snapshot if it exists and is fresh, with in-memory expiry set accordingly."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = (time.time() if now is None else now) - float(body.get("saved_at", 0))
    if not 0 <= age < max_age or not body.get("entries"):
        return None
    expires = time.monotonic() + (max_age - age)
    cache = {
        (e["path"], tuple(tuple(p) for p in e["params"])): (expires, e["data"])
        for e in body["entries"]
    }
    return {"cache": cache, "index": body.get("index")}


async def fetch(client: CarHaulerClient) -> Snapshot:
    index = await VehicleResolver(client).model_index()
    return {"cache": client.export_cache(), "index": index}


_lock = threading.Lock()
_snapshot: Snapshot | None = None


def warm(path: Path | None = None) -> Snapshot:
    """Once per process: the file if fresh, otherwise fetch (69 calls) and save it. Never
    raises; on failure calls start cold and the resolver fetches what it needs."""
    global _snapshot
    path = path or cache_file()
    with _lock:
        if _snapshot is not None:
            return _snapshot
        snap = load(path)
        if snap:
            logger.info("catalog loaded from %s (%d entries)", path, len(snap["cache"]))
        else:

            async def _fetch() -> Snapshot:
                client = CarHaulerClient()
                try:
                    return await fetch(client)
                finally:
                    await client.aclose()

            try:
                snap = asyncio.run(_fetch())
            except Exception:
                # Don't retry in this process: each attempt spends calls (e.g. a 402 when the
                # allowance is used up). Calls start cold and fetch only what they need.
                logger.exception("catalog warm-up failed; calls start cold")
                _snapshot = EMPTY
                return EMPTY
            try:
                save(path, snap)
            except OSError:
                logger.warning("couldn't save the catalog to %s", path)
            logger.info("catalog fetched (%d entries) and saved", len(snap["cache"]))
        _snapshot = snap
        return snap
