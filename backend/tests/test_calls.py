import pytest
from fastapi.testclient import TestClient

from app import calls, db
from app.main import app

ROOM = "call-0123456789ab"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    with TestClient(app) as c:
        yield c


def test_feedback_is_saved_under_the_call(client):
    res = client.post(
        f"/api/calls/{ROOM}/feedback",
        json={"rating": 4, "comment": "  She talked over me once. ", "persona": "Busy dad"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["comment"] == "She talked over me once."
    rows = db.query(f"CALL#{ROOM}", "FEEDBACK#")
    assert [(r["rating"], r["persona"]) for r in rows] == [(4, "Busy dad")]


def test_feedback_works_before_the_call_record_exists(client):
    # The browser shows the form as the call ends; the worker may still be saving the record.
    assert db.get(f"CALL#{ROOM}", "RECORD") is None
    assert client.post(f"/api/calls/{ROOM}/feedback", json={"rating": 5}).status_code == 201


@pytest.mark.parametrize("room", ["call-XYZ", "other-0123456789ab", "call-0123456789abcdef0"])
def test_unknown_room_names_are_rejected(client, room):
    assert client.post(f"/api/calls/{room}/feedback", json={"rating": 3}).status_code == 404


@pytest.mark.parametrize(
    "body", [{"rating": 0}, {"rating": 6}, {}, {"rating": 3, "comment": "x" * 2001}]
)
def test_invalid_feedback_is_rejected(client, body):
    assert client.post(f"/api/calls/{ROOM}/feedback", json=body).status_code == 422


def test_feedback_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(calls, "FEEDBACK_PER_IP_PER_HOUR", 2)
    codes = [
        client.post(f"/api/calls/{ROOM}/feedback", json={"rating": 3}).status_code for _ in range(3)
    ]
    assert codes == [201, 201, 429]


def _save_call(room: str, started_at: str, **extra) -> None:
    db.put(
        f"CALL#{room}", "RECORD", {"room": room, "started_at": started_at, "events": [], **extra}
    )
    db.put("CALLS", f"{started_at}#{room}", {"room": room, "started_at": started_at})


def test_call_list_is_newest_first(client):
    _save_call("call-aaaaaaaa", "2026-11-09T10:00:00+00:00")
    _save_call("call-bbbbbbbb", "2026-11-09T12:00:00+00:00")
    rooms = [c["room"] for c in client.get("/api/calls").json()]
    assert rooms == ["call-bbbbbbbb", "call-aaaaaaaa"]
    assert [c["room"] for c in client.get("/api/calls?limit=1").json()] == ["call-bbbbbbbb"]


def test_call_record_with_its_feedback(client):
    _save_call("call-aaaaaaaa", "2026-11-09T10:00:00+00:00", stage="quoted", duration_s=61.5)
    client.post("/api/calls/call-aaaaaaaa/feedback", json={"rating": 4, "comment": "nice"})
    body = client.get("/api/calls/call-aaaaaaaa").json()
    assert body["stage"] == "quoted" and body["duration_s"] == 61.5
    assert [(f["rating"], f["comment"]) for f in body["feedback"]] == [(4, "nice")]


def test_unknown_call_is_404(client):
    assert client.get("/api/calls/call-cccccccc").status_code == 404
    assert client.get("/api/calls/not-a-room").status_code == 404


def test_reads_are_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(calls, "READS_PER_IP_PER_HOUR", 2)
    assert [client.get("/api/calls").status_code for _ in range(3)] == [200, 200, 429]
