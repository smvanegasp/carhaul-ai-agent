"""The noisy-call harness (evals/noisy_calls.py, mia/smoke.py): mixing and scoring, offline."""

from __future__ import annotations

import numpy as np

from evals import noisy_calls
from mia import smoke


def test_noise_is_added_under_the_voice_and_loops():
    voice = np.array([100, -100, 0, 32000], dtype=np.int16).tobytes()
    noise = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    mixed = np.frombuffer(smoke.mix(voice, noise, at=2), dtype=np.int16)
    assert mixed.tolist() == [103, -99, 2, 32003]  # noise[2], noise[0], noise[1], noise[2]
    loud = np.frombuffer(smoke.mix(voice, noise * 1000, at=0), dtype=np.int16)
    assert loud[-1] == 32767  # clipped, not wrapped
    assert smoke.mix(voice, None, at=0) == voice


def test_the_grid_has_quiet_controls_first():
    cases = noisy_calls.grid(["classroom"], [12, 5], ["baseline", "full"], quiet=True)
    assert [c.key for c in cases] == [
        "quiet/baseline",
        "quiet/full",
        "classroom@12dB/baseline",
        "classroom@12dB/full",
        "classroom@5dB/baseline",
        "classroom@5dB/full",
    ]


def _result(responses, heard, events):
    return {
        "greeted": True,
        "lines": ["From Miami to Boston.", "A 2020 Camry."],
        "responses": responses,
        "hung_up": True,
        "heard": [{"who": "caller", "text": t, "t": 0} for t in heard],
        "events": events,
    }


def test_a_call_mia_answered_and_heard_cleanly():
    events = [
        {"type": "tool", "name": "save_origin_destination", "ok": True},
        {"type": "tool", "name": "save_vehicle", "ok": True},
        {"type": "turn", "role": "mia", "interrupted": False},
    ]
    s = noisy_calls.score(_result([1.2, 1.6], ["from miami to boston", "a 2020 camry"], events))
    assert s["answered"] == 2 and s["p50_s"] == 1.4
    assert s["route"] and s["vehicle"] and s["recall"] == 1.0 and s["extra_words"] == 0
    assert s["cut_off"] == 0 and not s["noisy_mode"]


def test_a_noisy_call_counts_what_went_wrong():
    events = [
        {"type": "tool", "name": "save_origin_destination", "ok": False},
        {"type": "turn", "role": "mia", "interrupted": True},
        {"type": "turn", "role": "mia", "interrupted": True},
        {"type": "tool", "name": "end_long_turn", "ok": True},
        {"type": "tool", "name": "noisy_mode", "ok": True},
    ]
    heard = ["did you finish the reading from miami"]
    s = noisy_calls.score(_result([None, 3.0], heard, events))
    assert s["answered"] == 1 and s["p50_s"] == 3.0
    assert not s["route"] and not s["vehicle"]
    assert s["cut_off"] == 2 and s["long_turns"] == 1 and s["noisy_mode"]
    assert s["extra_words"] == 5  # did you finish the reading
    assert s["recall"] == round(2 / 7, 2)  # from, miami of 7 distinct script words
