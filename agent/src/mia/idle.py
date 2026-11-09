"""The worker exits when nobody needs it, so on AWS it costs money only around calls.

On ECS the worker is a one-off task started by the API's ``/api/wake`` (backend/app/worker.py)
when someone opens the call page. It shuts itself down (a SIGTERM to its own process: LiveKit's
normal graceful shutdown, then the container exits and Fargate billing stops) when:

- no call is running, and the last call ended, the last wake and the start are all more than
  ``MIA_IDLE_EXIT_SECONDS`` ago (default 10 minutes); or
- it has been up ``MIA_MAX_UPTIME_SECONDS`` (2 hours) and no call is running: a cost guard
  against a page left open that keeps waking it.

Off unless ``MIA_IDLE_EXIT_SECONDS`` is set (docker compose and ``dev`` keep running).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from mia import records

logger = logging.getLogger("mia.idle")

CHECK_SECONDS = 15
WAKE_KEY = {"pk": "WORKER", "sk": "WAKE"}


@dataclass
class IdleTimer:
    idle_exit: float
    max_uptime: float = 2 * 3600
    started: float = field(default_factory=time.time)
    last_busy: float = 0.0

    def should_exit(self, now: float, active_calls: int, last_wake: float | None) -> str | None:
        """Why to exit now, or None to keep running."""
        if active_calls:
            self.last_busy = now
            return None
        if now - self.started >= self.max_uptime:
            return f"up {self.max_uptime / 3600:g} h with no call running"
        last = max(self.started, self.last_busy, last_wake or 0)
        if now - last >= self.idle_exit:
            return f"idle for {self.idle_exit:.0f} s"
        return None


def last_wake() -> float | None:
    """When the call page last asked for the worker (stamped by the API), if we can tell."""
    if not records.configured():
        return None
    try:
        item = records._table().get_item(Key=WAKE_KEY).get("Item")
        return float(item["at"]) if item else None
    except Exception:
        logger.warning("couldn't read the last wake", exc_info=True)
        return None


def install(server, exit_fn: Callable[[], None] | None = None) -> None:
    """Watch the worker's calls from its main process; exit when idle (see module docstring)."""
    idle_exit = os.environ.get("MIA_IDLE_EXIT_SECONDS")
    if not idle_exit:
        return
    timer = IdleTimer(
        idle_exit=float(idle_exit),
        max_uptime=float(os.environ.get("MIA_MAX_UPTIME_SECONDS") or 2 * 3600),
    )
    exit_fn = exit_fn or (lambda: os.kill(os.getpid(), signal.SIGTERM))

    async def watch() -> None:
        while True:
            await asyncio.sleep(CHECK_SECONDS)
            wake = await asyncio.to_thread(last_wake)
            why = timer.should_exit(time.time(), len(server.active_jobs), wake)
            if why:
                logger.info("worker exiting: %s", why)
                exit_fn()
                return

    tasks: list[asyncio.Task] = []
    # "worker_started" fires inside the worker's event loop, so the watcher can run there.
    server.on("worker_started", lambda: tasks.append(asyncio.create_task(watch())))
