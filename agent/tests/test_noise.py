"""Noisy places (noise.py): the filter choice, noisy-call mode, the long-turn cutoff."""

from __future__ import annotations

from types import SimpleNamespace

from fake_geo import fake_city_to_zip
from livekit import rtc
from livekit.agents.llm import ChatMessage
from livekit.agents.voice import UserTurnExceededEvent
from livekit.plugins import noise_cancellation
from scripted_llm import ScriptedLLM, Step

from mia import noise
from mia.agent import Mia, new_session
from mia.prompt import GREETINGS
from mia.state import QuoteSession
from mia.tools import Services

ROUTE_Q = "Where are you shipping the car from, and where is it going?"


def test_every_layer_is_on_unless_a_profile_says_otherwise(monkeypatch):
    monkeypatch.delenv("MIA_NOISE_HANDLING", raising=False)
    assert noise.profile() == "full" and noise.profile("nonsense") == "full"
    assert noise.profile(None) == "full" and noise.profile(3) == "full"
    assert noise.turn_limit("full") == {"max_duration": noise.TURN_LIMIT_S}
    monkeypatch.setenv("MIA_NOISE_HANDLING", "Baseline")
    assert noise.profile() == "baseline"
    assert noise.profile("filter") == "filter"  # a test call's request wins
    assert noise.noise_filter("baseline") is None
    assert noise.turn_limit("filter") == {} and noise.turn_limit("baseline") == {}
    monkeypatch.setattr(noise.sys, "platform", "linux")
    assert noise.noise_filter("filter") is not None


def test_never_on_windows(monkeypatch):
    # The filter crashes the worker on Windows (noise.noise_filter); Linux only.
    monkeypatch.setattr(noise.sys, "platform", "win32")
    assert noise.noise_filter("full") is None
    assert noise.turn_limit("full")  # the other layers stay


def test_a_phone_line_gets_the_telephony_model(monkeypatch):
    monkeypatch.setattr(noise.sys, "platform", "linux")
    pick = noise.noise_filter("full")

    def params(kind):
        return SimpleNamespace(participant=SimpleNamespace(kind=kind), track=None)

    sip = pick(params(rtc.ParticipantKind.PARTICIPANT_KIND_SIP))
    browser = pick(params(rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD))
    # The plugin's factories return options naming the model file.
    assert sip.options == noise_cancellation.BVCTelephony().options
    assert browser.options == noise_cancellation.BVC().options
    assert sip.options != browser.options


def test_noisy_mode_after_three_signs_and_only_once():
    state, watch = QuoteSession(), noise.NoiseWatch()
    assert not watch.signal(state, "interrupted")
    assert not watch.signal(state, "long_turn")
    assert watch.signal(state, "interrupted")  # the third switches
    assert state.noisy and state.noisy_line_due and state.noise_signals == 3
    assert not watch.signal(state, "interrupted")  # already noisy
    assert state.noise_signals == 4
    assert state.to_record()["noisy"] is True


def test_the_noisy_line_is_said_once_before_the_answer():
    state = QuoteSession(noisy=True, noisy_line_due=True)
    assert noise.with_noisy_line("", state) == ""  # nothing spoken: wait for a real line
    assert noise.with_noisy_line(ROUTE_Q, state) == f"{noise.NOISY_LINE} {ROUTE_Q}"
    assert noise.with_noisy_line(ROUTE_Q, state) == ROUTE_Q


async def test_noisy_mode_changes_the_live_options():
    handling = {
        "interruption": {"min_words": noise.NORMAL_MIN_WORDS},
        "user_turn_limit": noise.turn_limit("full"),
    }
    async with new_session(QuoteSession(), llm=ScriptedLLM([]), turn_handling=handling) as s:
        assert s.options.turn_handling["user_turn_limit"]["max_duration"] == 25.0
        noise.go_noisy(s.options.turn_handling)
        # The same dicts LiveKit reads on every interruption check and transcript.
        assert s.options.interruption["min_words"] == noise.NOISY_MIN_WORDS
        assert s.options.turn_handling["user_turn_limit"]["max_duration"] == 12.0


def test_the_normal_limit_is_longer_than_any_real_turn():
    # 23.9 s was the longest caller turn in 48 real calls (2026-11-12): don't cut those off.
    assert noise.TURN_LIMIT_S > 23.9
    assert noise.NOISY_TURN_LIMIT_S < noise.TURN_LIMIT_S


def test_no_turn_limit_stays_none():
    handling = {"interruption": {"min_words": 1}, "user_turn_limit": {"max_duration": None}}
    noise.go_noisy(handling)
    assert handling["user_turn_limit"]["max_duration"] is None


async def test_mia_says_its_noisy_before_her_next_answer(client, resolver):
    state = QuoteSession(noisy=True, noisy_line_due=True)
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=ScriptedLLM([Step(text=ROUTE_Q)])) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        result = await session.run(user_input="hello?")
    spoken = " ".join(
        e.item.text_content
        for e in result.events
        if isinstance(e.item, ChatMessage) and e.item.role == "assistant"
    )
    assert spoken.startswith(noise.NOISY_LINE)
    assert not state.noisy_line_due


async def test_a_turn_past_the_limit_is_answered_with_tools(client, resolver):
    # A classroom: the caller's turn never ends. Mia must answer through the normal pipeline
    # (commit the turn), not LiveKit's default tool-less reply.
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    signs: list[str] = []
    services.on_noise = signs.append
    mia = Mia(services, greeting=GREETINGS[0])
    commits: list[bool] = []
    fake_session = SimpleNamespace(commit_user_turn=lambda **_: commits.append(True))
    ev = UserTurnExceededEvent(
        transcript="from Miami to Boston",
        accumulated_transcript="so anyway from Miami to Boston",
        accumulated_word_count=6,
        duration=12.4,
    )
    Mia.session = property(lambda _self: fake_session)  # no running session needed
    try:
        await mia.on_user_turn_exceeded(ev)
    finally:
        del Mia.session
    assert commits == [True]
    assert signs == ["long_turn"]
    event = services.events.events[-1]
    assert event["name"] == "end_long_turn" and event["args"]["seconds"] == 12.4
