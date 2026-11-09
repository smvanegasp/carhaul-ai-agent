"""The idle exit that makes the on-demand worker cheap (mia/idle.py)."""

import asyncio

from mia import idle

T0 = 1_000_000.0


def test_runs_while_calls_are_active_then_exits_after_the_idle_time():
    timer = idle.IdleTimer(idle_exit=600, started=T0)
    assert timer.should_exit(T0 + 100, active_calls=1, last_wake=None) is None
    assert timer.should_exit(T0 + 650, active_calls=0, last_wake=None) is None  # call at +100
    assert timer.should_exit(T0 + 700, active_calls=0, last_wake=None) == "idle for 600 s"


def test_a_recent_wake_keeps_it_up():
    # The page opened (and woke it) 5 minutes ago: the caller may be about to call.
    timer = idle.IdleTimer(idle_exit=600, started=T0)
    assert timer.should_exit(T0 + 900, active_calls=0, last_wake=T0 + 600) is None
    assert timer.should_exit(T0 + 1200, active_calls=0, last_wake=T0 + 600) is not None


def test_a_fresh_worker_gets_the_full_idle_time():
    timer = idle.IdleTimer(idle_exit=600, started=T0)
    assert timer.should_exit(T0 + 30, active_calls=0, last_wake=None) is None


def test_max_uptime_wins_over_wakes_but_never_cuts_a_call():
    timer = idle.IdleTimer(idle_exit=600, max_uptime=3600, started=T0)
    assert timer.should_exit(T0 + 3700, active_calls=1, last_wake=T0 + 3690) is None
    assert "no call running" in timer.should_exit(T0 + 3710, 0, last_wake=T0 + 3700)


def test_install_is_off_without_the_setting(monkeypatch):
    monkeypatch.delenv("MIA_IDLE_EXIT_SECONDS", raising=False)

    class Server:
        def on(self, *_):
            raise AssertionError("should not watch")

    idle.install(Server())


async def test_the_watcher_exits_the_worker_when_idle(monkeypatch):
    monkeypatch.setenv("MIA_IDLE_EXIT_SECONDS", "0")
    monkeypatch.setattr(idle, "CHECK_SECONDS", 0)
    monkeypatch.setattr(idle, "last_wake", lambda: None)
    exited = asyncio.Event()

    class Server:
        active_jobs: list = []

        def on(self, event, fn):
            assert event == "worker_started"
            self.start = fn

    server = Server()
    idle.install(server, exit_fn=exited.set)
    server.start()
    await asyncio.wait_for(exited.wait(), 2)


def test_last_wake_reads_the_apis_stamp(table):
    assert idle.last_wake() is None
    table.put_item(Item={"pk": "WORKER", "sk": "WAKE", "at": 123})
    assert idle.last_wake() == 123.0
