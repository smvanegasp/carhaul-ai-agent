import pytest
from fastapi.testclient import TestClient
from livekit import api

from app import ratelimit
from app.main import app

KEY, SECRET = "devkey", "a-test-secret-that-is-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", KEY)
    monkeypatch.setenv("LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setenv("CALLS_PER_IP_PER_HOUR", "3")
    monkeypatch.setenv("CALLS_PER_DAY", "5")
    ratelimit.reset()
    with TestClient(app) as c:
        yield c
    ratelimit.reset()


def _claims(token: str):
    return api.TokenVerifier(KEY, SECRET).verify(token)


def test_token_joins_its_own_room_and_dispatches_mia(client):
    body = client.post("/api/token").json()
    assert body["server_url"] == "wss://example.livekit.cloud"
    assert body["room_name"].startswith("call-")
    claims = _claims(body["participant_token"])
    assert claims.video.room == body["room_name"] and claims.video.room_join
    assert claims.video.can_publish_sources == ["microphone"]
    assert not claims.video.room_admin
    assert [a.agent_name for a in claims.room_config.agents] == ["mia"]
    assert claims.room_config.max_participants == 2


def test_every_call_gets_a_new_room(client):
    rooms = {client.post("/api/token").json()["room_name"] for _ in range(3)}
    assert len(rooms) == 3


def test_rate_limit_per_ip(client):
    for _ in range(3):
        assert client.post("/api/token").status_code == 200
    r = client.post("/api/token")
    assert r.status_code == 429 and "a bit" in r.json()["detail"]
    # Another viewer (behind a proxy) can still call.
    other = client.post("/api/token", headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200


def test_daily_cap_across_ips(client):
    for i in range(5):
        ip = f"203.0.113.{i}"
        assert client.post("/api/token", headers={"X-Forwarded-For": ip}).status_code == 200
    r = client.post("/api/token", headers={"X-Forwarded-For": "198.51.100.1"})
    assert r.status_code == 429 and "today" in r.json()["detail"]


def test_spoofed_forwarded_for_uses_the_proxys_entry(client):
    # The client can send its own X-Forwarded-For; the proxy appends the real address last.
    for _ in range(3):
        h = {"X-Forwarded-For": f"10.0.0.{_}, 198.51.100.7"}
        assert client.post("/api/token", headers=h).status_code == 200
    h = {"X-Forwarded-For": "10.0.0.99, 198.51.100.7"}
    assert client.post("/api/token", headers=h).status_code == 429


def test_not_configured(client, monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_SECRET")
    assert client.post("/api/token").status_code == 503
