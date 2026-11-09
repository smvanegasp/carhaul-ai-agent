from mia.latency import CallLatency


def test_keeps_each_sides_metrics():
    lat = CallLatency()
    lat.on_message("user", {"end_of_turn_delay": 0.58, "transcription_delay": 0.3})
    lat.on_message(
        "assistant",
        {"e2e_latency": 0.73, "llm_node_ttft": 0.28, "tts_node_ttfb": 0.18, "playback": 0},
    )
    s = lat.summary()
    assert s["end_of_turn_delay"]["p50_ms"] == 580
    assert s["e2e_latency"]["p50_ms"] == 730
    assert s["tts_node_ttfb"]["n"] == 1


def test_greeting_without_metrics_and_other_roles_are_ignored():
    lat = CallLatency()
    lat.on_message("assistant", None)  # the greeting: nobody spoke before it
    lat.on_message("system", {"e2e_latency": 1.0})
    lat.on_message("assistant", {"e2e_latency": -1})
    assert lat.summary()["e2e_latency"] is None


def test_summary_percentiles_in_ms():
    lat = CallLatency()
    for d in (0.2, 0.4, 0.9):
        lat.on_message("assistant", {"e2e_latency": d})
    assert lat.summary()["e2e_latency"] == {"n": 3, "p50_ms": 400, "p90_ms": 900, "mean_ms": 500}
