"""POST /api/wake: starting the on-demand voice worker (a fake ECS client, moto DynamoDB)."""

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import db, worker
from app.main import app


class FakeECS:
    """Just enough of the ECS API: tasks are dicts with lastStatus and healthStatus."""

    def __init__(self, tasks=None, fail=False):
        self.tasks = tasks or []
        self.started = []
        self.fail = fail

    def list_tasks(self, **kw):
        assert kw["desiredStatus"] == "RUNNING" and kw["family"] == "carhaul-agent"
        return {"taskArns": [f"arn:task/{i}" for i in range(len(self.tasks))]}

    def describe_tasks(self, **kw):
        return {"tasks": self.tasks}

    def run_task(self, **kw):
        if self.fail:
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "RunTask")
        self.started.append(kw)
        self.tasks.append({"lastStatus": "PROVISIONING"})


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("AGENT_CLUSTER", "carhaul")
    monkeypatch.setenv("AGENT_SUBNETS", "subnet-a,subnet-b")
    monkeypatch.setenv("AGENT_SECURITY_GROUP", "sg-1")


def _client(monkeypatch, ecs: FakeECS) -> TestClient:
    monkeypatch.setattr(worker, "ecs_client", lambda: ecs)
    return TestClient(app)


def test_locally_the_worker_is_always_ready(monkeypatch):
    monkeypatch.delenv("AGENT_CLUSTER", raising=False)
    monkeypatch.delenv("ORIGIN_SECRET", raising=False)
    assert TestClient(app).post("/api/wake").json()["state"] == "ready"


def test_no_worker_starts_one(aws_env, monkeypatch):
    ecs = FakeECS()
    body = _client(monkeypatch, ecs).post("/api/wake").json()
    assert body["state"] == "starting"
    [run] = ecs.started
    assert run["taskDefinition"] == "carhaul-agent" and run["launchType"] == "FARGATE"
    net = run["networkConfiguration"]["awsvpcConfiguration"]
    assert net["subnets"] == ["subnet-a", "subnet-b"] and net["assignPublicIp"] == "ENABLED"
    # The wake is stamped for the worker's idle timer.
    assert db.get("WORKER", "WAKE")["at"] > 0


def test_polling_while_it_starts_doesnt_start_another(aws_env, monkeypatch):
    ecs = FakeECS()
    client = _client(monkeypatch, ecs)
    states = [client.post("/api/wake").json()["state"] for _ in range(3)]
    assert states == ["starting"] * 3
    assert len(ecs.started) == 1


def test_two_pages_at_once_start_one_worker(aws_env, monkeypatch):
    # Both see no task yet (ListTasks lags behind RunTask); the lock row lets one through.
    ecs = FakeECS()
    monkeypatch.setattr(worker, "worker_state", lambda _ecs: "off")
    client = _client(monkeypatch, ecs)
    assert [client.post("/api/wake").json()["state"] for _ in range(2)] == ["starting"] * 2
    assert len(ecs.started) == 1


def test_healthy_worker_is_ready(aws_env, monkeypatch):
    ecs = FakeECS([{"lastStatus": "RUNNING", "healthStatus": "HEALTHY"}])
    assert _client(monkeypatch, ecs).post("/api/wake").json()["state"] == "ready"
    assert ecs.started == []


def test_running_but_not_registered_yet_is_starting(aws_env, monkeypatch):
    ecs = FakeECS([{"lastStatus": "RUNNING", "healthStatus": "UNKNOWN"}])
    assert _client(monkeypatch, ecs).post("/api/wake").json()["state"] == "starting"


def test_starts_are_capped_per_day(aws_env, monkeypatch):
    monkeypatch.setenv("WORKER_STARTS_PER_DAY", "1")
    monkeypatch.setattr(worker, "START_LOCK_SECONDS", -1)  # no lock between the two starts
    ecs = FakeECS()
    monkeypatch.setattr(worker, "worker_state", lambda _ecs: "off")
    client = _client(monkeypatch, ecs)
    assert client.post("/api/wake").json()["state"] == "starting"
    body = client.post("/api/wake").json()
    assert body["state"] == "unavailable" and "tomorrow" in body["detail"]
    assert len(ecs.started) == 1


def test_an_aws_error_is_reported_not_raised(aws_env, monkeypatch):
    body = _client(monkeypatch, FakeECS(fail=True)).post("/api/wake").json()
    assert body["state"] == "unavailable"


def test_wakes_are_rate_limited_per_ip(aws_env, monkeypatch):
    monkeypatch.setattr(worker, "WAKES_PER_IP_PER_HOUR", 2)
    ecs = FakeECS([{"lastStatus": "RUNNING", "healthStatus": "HEALTHY"}])
    client = _client(monkeypatch, ecs)
    codes = [client.post("/api/wake").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
