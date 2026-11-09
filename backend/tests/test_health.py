import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_origin_secret_required_when_set(client, monkeypatch):
    monkeypatch.setenv("ORIGIN_SECRET", "s3cret")
    assert client.get("/api/health").status_code == 403
    ok = client.get("/api/health", headers={"X-Origin-Verify": "s3cret"})
    assert ok.status_code == 200
