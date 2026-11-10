"""POST /api/wake: Mia's voice worker runs only when someone wants to call.

On AWS the worker is a single ECS Fargate task that nobody keeps running (infra/agent.tf). The
call page calls this endpoint when it opens and again right before a call:

- no worker running → start one (``ecs:RunTask``) and answer ``starting``
- a worker starting (or not registered with LiveKit yet) → ``starting``, with a ``step`` for the
  page's progress bar: ``server`` while ECS finds a machine and pulls the image (PROVISIONING,
  PENDING; about the first half of the ~1 min start), ``loading`` once the container runs and
  Mia loads her models and registers with LiveKit
- a worker running and healthy → ``ready`` (its health check only passes once it's
  registered with LiveKit, so a call placed now gets Mia)

Every wake also stamps ``WORKER`` / ``WAKE`` in DynamoDB. The worker exits after 10 minutes with
no calls and no wake (``agent/src/mia/idle.py``), so an open page keeps it up a while and an
empty site costs nothing. Starts are capped per day (``WORKER_STARTS_PER_DAY``), and a lock row
keeps two pages from starting two workers at once.

Locally (no ``AGENT_CLUSTER``) docker compose runs the worker, so this always answers ``ready``.
"""

import logging
import os
import time
from functools import lru_cache
from typing import Literal

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import db, ratelimit

router = APIRouter()
log = logging.getLogger("uvicorn.error")

WAKES_PER_IP_PER_HOUR = 240  # the page polls every few seconds while Mia starts
START_LOCK_SECONDS = 180  # a starting task shows up in ListTasks well before this


Step = Literal["server", "loading"]


class WakeStatus(BaseModel):
    state: Literal["ready", "starting", "unavailable"]
    detail: str = ""
    step: Step | None = None  # only while starting


def configured() -> bool:
    return bool(os.environ.get("AGENT_CLUSTER"))


@lru_cache
def ecs_client():
    return boto3.client("ecs", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def _cluster() -> str:
    return os.environ["AGENT_CLUSTER"]


def _family() -> str:
    return os.environ.get("AGENT_TASK_FAMILY", "carhaul-agent")


def worker_state(ecs) -> Literal["ready", "server", "loading", "off"]:
    """``server`` and ``loading`` are the two steps of ``starting`` (see the module docstring)."""
    arns = ecs.list_tasks(cluster=_cluster(), family=_family(), desiredStatus="RUNNING")["taskArns"]
    if not arns:
        return "off"
    tasks = ecs.describe_tasks(cluster=_cluster(), tasks=arns)["tasks"]
    if any(t.get("lastStatus") == "RUNNING" and t.get("healthStatus") == "HEALTHY" for t in tasks):
        return "ready"
    if any(t.get("lastStatus") in ("ACTIVATING", "RUNNING") for t in tasks):
        return "loading"
    return "server"


def _take_start_lock(now: int) -> bool:
    """True if this request may start the worker (no other start in the last 3 minutes)."""
    try:
        db.get_table().put_item(
            Item={"pk": "WORKER", "sk": "STARTING", "until": now + START_LOCK_SECONDS},
            ConditionExpression="attribute_not_exists(pk) OR #until < :now",
            ExpressionAttributeNames={"#until": "until"},
            ExpressionAttributeValues={":now": now},
        )
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def start(ecs) -> None:
    ecs.run_task(
        cluster=_cluster(),
        taskDefinition=_family(),  # the latest revision, which runs the ":latest" image
        launchType="FARGATE",
        count=1,
        startedBy="carhaul-api",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": os.environ["AGENT_SUBNETS"].split(","),
                "securityGroups": [os.environ["AGENT_SECURITY_GROUP"]],
                # Public IP instead of a NAT gateway: the worker only connects out.
                "assignPublicIp": "ENABLED",
            }
        },
    )


@router.post("/api/wake")
def wake(request: Request) -> WakeStatus:
    if ratelimit.hit(f"wake-ip#{ratelimit.client_ip(request)}", 3600) > WAKES_PER_IP_PER_HOUR:
        raise ratelimit.too_many("Too many requests. Try again in a bit.")
    if not configured():
        return WakeStatus(state="ready")

    now = int(time.time())
    db.put("WORKER", "WAKE", {"at": now})
    ecs = ecs_client()
    try:
        state = worker_state(ecs)
        if state == "ready":
            return WakeStatus(state="ready")
        if state != "off":
            return WakeStatus(state="starting", step=state)
        if not _take_start_lock(now):
            return WakeStatus(state="starting", step="server")
        starts_per_day = int(os.environ.get("WORKER_STARTS_PER_DAY") or 20)
        if ratelimit.hit("worker-starts", 86400) > starts_per_day:
            return WakeStatus(
                state="unavailable", detail="Mia is resting for today. Try again tomorrow!"
            )
        start(ecs)
        log.info("Started the voice worker")
        return WakeStatus(state="starting", step="server")
    except ClientError:
        # The alarm on this line emails Sergio (infra/monitoring.tf).
        log.exception("Couldn't start the voice worker")
        return WakeStatus(state="unavailable", detail="Mia can't take calls right now.")
