"""What Mia does when the caller goes quiet (stage 8).

LiveKit marks the caller "away" after ``user_away_timeout`` (15 s) with both sides silent, and
starts counting again after Mia speaks. Seen on Sergio's calls (2026-11-09): after "anything
else?" a caller who said nothing kept Mia waiting until they hung up themselves.

- After the quote (or after a transfer that didn't go through), silence means they're done:
  a short goodbye, then Mia hangs up.
- Earlier, the first silence gets "Are you still there?"; a second one in a row, a goodbye
  and a hang-up.
- Never while a transfer is ringing or connected, or once the call is ending.

``main.py`` calls ``on_away`` from the session's ``user_state_changed`` event and resets the
count when the caller speaks.
"""

from __future__ import annotations

from mia.state import QuoteSession, Stage

STILL_THERE = "Are you still there?"
GOODBYE_DONE = "It sounds like you're all set. Thanks for calling F&F, goodbye!"
GOODBYE_SILENT = (
    "I can't hear you, so I'll end the call for now. Feel free to call back anytime. Goodbye!"
)


def on_away(state: QuoteSession, prompts: int) -> tuple[str, bool] | None:
    """What to say after a silence, and whether to hang up after it (None: say nothing).
    ``prompts``: how many silences in a row Mia has already answered."""
    if state.ended or state.transfer in ("pending", "connected"):
        return None
    if state.stage in (Stage.QUOTED, Stage.TRANSFER):
        return GOODBYE_DONE, True
    if prompts == 0:
        return STILL_THERE, False
    return GOODBYE_SILENT, True
