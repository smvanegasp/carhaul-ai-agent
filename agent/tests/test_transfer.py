"""The phone transfer's settings, Mia's handoff line, the daily cap and the dial request."""

from datetime import UTC, datetime

import pytest

from mia import prompt, transfer
from mia.state import Place, QuoteSession

BOS = Place("Boston", "MA", "Massachusetts", "02110")
SF = Place("San Francisco", "CA", "California", "94103")
ENV = {
    "TWILIO_SIP_ADDRESS": "carhaul-mia.pstn.twilio.com",
    "TWILIO_SIP_USERNAME": "mia-livekit",
    "TWILIO_SIP_PASSWORD": "pw",
    "TRANSFER_PHONE_NUMBER": "+15555550100",
    "TRANSFER_CALLER_ID": "+15555550199",
}


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def test_config_from_env(env):
    config = transfer.Config.from_env()
    assert config and config.phone == "+15555550100" and config.caller_id == "+15555550199"


def test_no_config_when_anything_is_missing(env, monkeypatch):
    monkeypatch.delenv("TRANSFER_CALLER_ID")
    assert transfer.Config.from_env() is None


def test_calling_from_the_number_being_called_is_refused(env, monkeypatch):
    # A phone calling itself goes to voicemail (the first test call, 2026-11-09).
    monkeypatch.setenv("TRANSFER_CALLER_ID", ENV["TRANSFER_PHONE_NUMBER"])
    assert transfer.Config.from_env() is None


def test_dial_request(env):
    req = transfer.dial_request(transfer.Config.from_env(), "call-abc")
    assert req.room_name == "call-abc" and req.sip_call_to == "+15555550100"
    assert req.sip_number == "+15555550199"  # the caller ID the phone shows
    assert req.trunk.hostname == "carhaul-mia.pstn.twilio.com"
    assert req.wait_until_answered and req.play_dialtone
    assert req.ringing_timeout.seconds == transfer.RING_SECONDS
    assert req.max_call_duration.seconds == transfer.MAX_TRANSFER_MINUTES * 60


def test_handoff_line_tells_the_representative_what_the_call_is_about():
    s = QuoteSession(origin=BOS, destination=SF)
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    s.quote = {"total": 1291}
    line = transfer.handoff_line(s)
    assert "2025 Honda Civic" in line and "Boston, Massachusetts" in line
    assert "1,291 dollars" in line and line.endswith("Goodbye!")


def test_handoff_line_with_nothing_on_file():
    assert transfer.handoff_line(QuoteSession()).startswith("Hi, this is Mia from F&F.")


def test_daily_cap_without_dynamodb(monkeypatch):
    monkeypatch.delenv("TABLE_NAME", raising=False)
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    monkeypatch.setattr(transfer, "_local_count", {})
    day = datetime(2026, 11, 9, tzinfo=UTC)
    taken = [transfer.take_slot(day) for _ in range(transfer.TRANSFERS_PER_DAY + 1)]
    assert taken == [True] * transfer.TRANSFERS_PER_DAY + [False]
    assert transfer.take_slot(datetime(2026, 11, 10, tzinfo=UTC))  # a new day


def test_mia_never_names_sergio():
    # Sergio (2026-11-09): "Sergio, who built this" sounded arrogant.
    for text in (prompt.INSTRUCTIONS, transfer.CONNECTING, transfer.NO_ANSWER):
        assert "Sergio" not in text


# --- screening: a person must press 1 (a voicemail also "answers") ---------------------------


def test_screening_line_asks_to_press_one():
    from mia.transfer import PRESS_ONE, screening_line

    s = QuoteSession()
    line = screening_line(s)
    assert line.startswith("Hi, this is Mia from F&F.")
    assert line.endswith(PRESS_ONE) and "Goodbye" not in line


async def _screen(press_after: int | None):
    """Run transfer.screen; the 1 arrives during the n-th spoken line (None: never)."""
    import asyncio

    from mia import transfer

    pressed, said = asyncio.Event(), []

    async def say(text):
        said.append(text)
        if press_after is not None and len(said) == press_after:
            pressed.set()

    ok = await transfer.screen(say, pressed, "intro", wait_s=0.05, again_s=0.05)
    return ok, said


async def test_a_person_who_presses_one_is_put_through():
    ok, said = await _screen(press_after=1)
    assert ok and said == ["intro"]


async def test_one_more_prompt_then_put_through():
    from mia.transfer import PRESS_ONE

    ok, said = await _screen(press_after=2)
    assert ok and said == ["intro", PRESS_ONE]


async def test_a_voicemail_never_presses_one():
    # Sergio's call, 2026-11-11: his voicemail answered and Mia introduced the caller to it.
    from mia.transfer import PRESS_ONE

    ok, said = await _screen(press_after=None)
    assert not ok and said == ["intro", PRESS_ONE]
