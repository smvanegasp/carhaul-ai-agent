"""What Mia does when the caller goes quiet (mia/silence.py)."""

from mia import silence
from mia.state import QuoteSession, Stage


def test_first_silence_checks_in_second_hangs_up():
    s = QuoteSession()
    assert silence.on_away(s, 0) == (silence.STILL_THERE, False)
    assert silence.on_away(s, 1) == (silence.GOODBYE_SILENT, True)


def test_silence_after_the_quote_means_theyre_done():
    # Sergio's call (2026-11-09): after "anything else?" Mia waited until the caller hung up.
    s = QuoteSession()
    s.advance(Stage.QUOTED)
    assert silence.on_away(s, 0) == (silence.GOODBYE_DONE, True)


def test_silence_after_a_transfer_that_didnt_connect():
    s = QuoteSession(transfer="no_answer")
    s.advance(Stage.TRANSFER)
    assert silence.on_away(s, 0) == (silence.GOODBYE_DONE, True)


def test_never_during_a_transfer_or_once_ending():
    assert silence.on_away(QuoteSession(transfer="pending"), 0) is None
    assert silence.on_away(QuoteSession(transfer="connected"), 0) is None
    assert silence.on_away(QuoteSession(ended=True), 0) is None
