"""Call events (live panel stream and call record) and the tool wrapper that emits them."""

from __future__ import annotations

import json

import pytest

from mia.agent import _run_tool
from mia.events import MAX_JSON_CHARS, CallEvents
from mia.state import QuoteSession
from mia.tools import Services


def test_turn_metrics_in_ms_by_role():
    events = CallEvents()
    events.turn(
        "user",
        "Miami to Boston",
        {
            "end_of_turn_delay": 0.577,
            "transcription_delay": 0.31,
            "started_speaking_at": 100.0,
            "stopped_speaking_at": 102.5,
            "llm_node_ttft": 9.9,  # a Mia metric on a caller line is ignored
        },
    )
    events.turn(
        "assistant",
        "Great.",
        {"llm_node_ttft": 0.25, "tts_node_ttfb": 0.17, "e2e_latency": 1.2},
        interrupted=True,
    )
    caller, mia = events.events
    assert caller["role"] == "caller"
    assert caller["metrics"] == {"end_of_turn": 577, "stt": 310}
    assert caller["speaking_s"] == 2.5
    assert mia["role"] == "mia" and mia["interrupted"] is True
    assert mia["metrics"] == {"llm_ttft": 250, "tts_ttfb": 170, "e2e": 1200}
    # The same values feed the per-call latency summary.
    assert events.latency.summary()["e2e_latency"]["p50_ms"] == 1200


def test_missing_and_negative_metrics_are_left_out():
    events = CallEvents()
    events.turn("assistant", "Hi", {"e2e_latency": -1, "llm_node_ttft": None})
    assert events.events[0]["metrics"] == {}
    assert events.events[0]["speaking_s"] is None


def test_events_are_numbered_and_sent_to_the_sink():
    sent = []
    events = CallEvents(sink=sent.append)
    events.config(llm="Groq x")
    events.turn("assistant", "Hi", kind="greeting")
    assert [e["seq"] for e in sent] == [0, 1]
    assert sent[1]["kind"] == "greeting"
    json.dumps(sent)  # what goes on the wire is plain JSON


def test_a_failing_sink_never_breaks_the_call():
    def boom(_event):
        raise RuntimeError("room gone")

    events = CallEvents(sink=boom)
    events.turn("assistant", "Hi")
    assert len(events.events) == 1


def test_huge_tool_results_are_capped():
    events = CallEvents()
    events.tool("save_vehicle", {"make": "Toyota"}, {"ok": True, "blob": "x" * 50_000}, 12.3)
    result = events.events[0]["result"]
    assert result["truncated"] is True
    assert len(result["start"]) == MAX_JSON_CHARS
    assert events.events[0]["ms"] == 12


def test_transcript_and_talk_time():
    events = CallEvents()
    events.turn("assistant", "Hi, I'm Mia.", kind="greeting")
    events.turn("user", "Hello", {"started_speaking_at": 1.0, "stopped_speaking_at": 2.0})
    events.tool("get_quote", {}, {"ok": True}, 5)
    events.turn("assistant", "Sure.", {"started_speaking_at": 3.0, "stopped_speaking_at": 4.5})
    assert [(t["role"], t["text"]) for t in events.transcript()] == [
        ("mia", "Hi, I'm Mia."),
        ("caller", "Hello"),
        ("mia", "Sure."),
    ]
    assert events.talk_seconds() == {"caller": 1.0, "mia": 1.5}


@pytest.fixture
def services(client, resolver):
    return Services(carhauler=client, resolver=resolver)


async def test_run_tool_reports_the_call_and_the_state(services):
    state = QuoteSession()

    async def tool():
        return {"ok": False, "error_code": "city_not_found", "next": "ask again"}

    out = await _run_tool(services, state, "save_origin_destination", {"origin_city": "X"}, tool())
    assert json.loads(out)["error_code"] == "city_not_found"
    tool_event, state_event = services.events.events
    assert tool_event["type"] == "tool" and tool_event["ok"] is False
    assert tool_event["args"] == {"origin_city": "X"}
    assert state_event["type"] == "state" and state_event["stage"] == "greeting"


async def test_run_tool_reports_a_crash_too(services):
    async def tool():
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        await _run_tool(services, QuoteSession(), "get_quote", {}, tool())
    assert services.events.events[0]["ok"] is False
    assert services.events.events[0]["result"] is None


def test_a_coded_line_in_the_chat_context_is_logged_once():
    # Silence and time-limit lines are logged when triggered, then LiveKit adds them to the
    # chat once spoken; the record showed "Are you still there?" twice (2026-11-10).
    events = CallEvents()
    events.turn("assistant", "Are you still there?", kind="silence")
    events.turn("assistant", "Are you still there?", {"tts_node_ttfb": 0.2})
    events.turn("assistant", "Are you still there?")  # Mia herself, later: a normal line
    kinds = [e["kind"] for e in events.events if e["type"] == "turn"]
    assert kinds == ["silence", "said"]
