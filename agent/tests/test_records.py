"""The call record: what it holds and how it lands in DynamoDB (moto, no AWS)."""

from __future__ import annotations

from decimal import Decimal

import boto3

from mia import records
from mia.events import CallEvents
from mia.state import Place, QuoteSession, Stage

ROOM = "call-0123456789ab"


def _call() -> tuple[QuoteSession, CallEvents]:
    state = QuoteSession()
    state.set_route(
        Place("Miami", "FL", "Florida", "33131"), Place("Boston", "MA", "Massachusetts", "02110")
    )
    state.add_vehicle(year=2020, make="Toyota", model="Camry", trim_id=1)
    state.quote = {"total": 724, "items": [{"vehicle": "the Toyota", "price": 724}]}
    state.advance(Stage.QUOTED)
    state.end_reason = "mia"
    events = CallEvents()
    events.turn("assistant", "Hi, I'm Mia.", kind="greeting")
    events.turn("user", "Miami to Boston", {"started_speaking_at": 1.0, "stopped_speaking_at": 3})
    events.tool("save_origin_destination", {"origin_city": "Miami"}, {"ok": True}, 210)
    events.tool("get_quote", {}, {"ok": False, "error_code": "carhauler_down"}, 900)
    events.turn("assistant", "It's $724.", {"e2e_latency": 1.25}, interrupted=True)
    events.end("mia", "quoted")
    return state, events


def test_record_has_everything_the_dashboard_needs():
    state, events = _call()
    record = records.build(ROOM, state, events)
    assert record["room"] == ROOM
    assert record["stage"] == "quoted"
    assert record["quote"]["total"] == 724
    assert [t["text"] for t in record["transcript"]] == [
        "Hi, I'm Mia.",
        "Miami to Boston",
        "It's $724.",
    ]
    assert record["talk_s"]["caller"] == 2
    assert record["interruptions"] == 1
    assert record["tool_calls"] == 2 and record["tool_errors"] == 1
    assert record["latency"]["e2e_latency"]["p50_ms"] == 1250
    assert len(record["events"]) == 6

    summary = records.summary(record)
    assert summary["quote_total"] == 724
    assert summary["vehicles"] == 1
    assert summary["e2e_p50_ms"] == 1250


def test_an_oversized_record_keeps_the_transcript_but_not_the_events(monkeypatch):
    monkeypatch.setattr(records, "MAX_RECORD_BYTES", 500)
    state, events = _call()
    record = records.build(ROOM, state, events)
    assert record["events"] == [] and record["events_dropped"] is True
    assert len(record["transcript"]) == 3


def test_not_configured_means_not_saved(monkeypatch):
    monkeypatch.delenv("TABLE_NAME", raising=False)
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    state, events = _call()
    assert records.save(records.build(ROOM, state, events)) is False


def test_save_writes_the_record_and_the_list_entry(table):
    state, events = _call()
    record = records.build(ROOM, state, events)
    assert records.save(record) is True

    saved = table.get_item(Key={"pk": f"CALL#{ROOM}", "sk": "RECORD"})["Item"]
    assert saved["quote"]["total"] == 724
    assert saved["duration_s"] == Decimal(str(record["duration_s"]))
    listed = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq("CALLS"))[
        "Items"
    ]
    assert [i["room"] for i in listed] == [ROOM]
    assert listed[0]["sk"].endswith(f"#{ROOM}")


def test_save_never_raises(table, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "no-such-table")
    records._table.cache_clear()
    state, events = _call()
    assert records.save(records.build(ROOM, state, events)) is False
