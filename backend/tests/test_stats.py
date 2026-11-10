"""GET /api/stats: per-call milestones and Mia's time, backfilled from records once."""

import pytest
from fastapi.testclient import TestClient

from app import db, stats
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    with TestClient(app) as c:
        yield c


def _tool(name, t, ok=True):
    return {"type": "tool", "name": name, "t": t, "ok": ok}


QUOTED = {
    "duration_s": 95.0,
    "origin": {"city": "Boston"},
    "destination": {"city": "San Francisco"},
    "vehicles": [{"make": "Honda"}],
    "quote": {"total": 1291},
    "transfer": None,
    "events": [_tool("save_origin_destination", 20), _tool("get_quote", 60)],
}
TRANSFERRED = {
    "duration_s": 300.0,
    "origin": None,
    "destination": None,
    "vehicles": [],
    "quote": None,
    "transfer": "connected",
    "events": [_tool("request_human", 30), _tool("dial_representative", 41.5)],
}


def _old_call(room, started_at, record):
    """A call saved before the worker wrote stats facts: only the old summary fields."""
    db.put(f"CALL#{room}", "RECORD", {"room": room, "started_at": started_at, **record})
    db.put(
        "CALLS",
        f"{started_at}#{room}",
        {"room": room, "started_at": started_at, "duration_s": record["duration_s"]},
    )


def test_milestones_and_mias_time():
    facts = stats.facts_from_record(QUOTED)
    assert {k: facts[k] for k in ("route", "vehicles", "quoted", "transfer", "mia_s")} == {
        "route": True,
        "vehicles": True,
        "quoted": True,
        "transfer": False,
        "mia_s": 95.0,
    }
    transferred = stats.facts_from_record(TRANSFERRED)
    # A transfer is a lead even without a quote; Mia's time stops at the handoff.
    assert transferred["transfer"] and not transferred["quoted"]
    assert transferred["mia_s"] == 41.5


@pytest.mark.parametrize(
    ("changes", "disposition"),
    [
        ({"transfer": "connected", "transfer_kind": "organic"}, "organic_transfer"),
        ({"transfer": "connected", "transfer_kind": "requested"}, "requested_transfer"),
        ({"transfer": "connected", "transfer_kind": "forced"}, "forced_transfer"),
        # Older records have no kind: after a quote it was the offer.
        ({"transfer": "connected"}, "organic_transfer"),
        ({"transfer": "no_answer", "end_reason": "caller"}, "hung_up_on_hold"),
        ({"transfer": "pending", "end_reason": "caller"}, "hung_up_on_hold"),
        ({"end_reason": "caller"}, "hung_up"),
        ({"end_reason": "mia"}, "not_interested"),
        ({"end_reason": "time_limit"}, "not_interested"),
    ],
)
def test_dispositions(changes, disposition):
    assert stats.facts_from_record({**QUOTED, **changes})["disposition"] == disposition


def test_an_old_transfer_before_any_quote_was_requested():
    assert stats.facts_from_record(TRANSFERRED)["disposition"] == "requested_transfer"


def test_old_calls_are_backfilled_once(client):
    _old_call("call-aaaaaaaa", "2026-11-09T10:00:00+00:00", QUOTED)
    _old_call("call-bbbbbbbb", "2026-11-09T11:00:00+00:00", TRANSFERRED)
    rows = client.get("/api/stats").json()
    assert [(r["room"], r["quoted"], r["transfer"]) for r in rows] == [
        ("call-bbbbbbbb", False, True),
        ("call-aaaaaaaa", True, False),
    ]
    saved = db.get("CALLS", "2026-11-09T10:00:00+00:00#call-aaaaaaaa")
    assert saved["stats_v"] == stats.STATS_V and saved["route"] is True


def test_test_calls_are_hidden_unless_asked(client):
    _old_call("smoke-cccccccc", "2026-11-09T12:00:00+00:00", QUOTED)
    assert client.get("/api/stats").json() == []
    [row] = client.get("/api/stats?include_tests=true").json()
    assert row["test"] is True


def test_a_row_whose_record_is_missing_is_skipped(client):
    db.put(
        "CALLS",
        "2026-11-09T13:00:00+00:00#call-dddddddd",
        {"room": "call-dddddddd", "started_at": "2026-11-09T13:00:00+00:00"},
    )
    assert client.get("/api/stats").json() == []
