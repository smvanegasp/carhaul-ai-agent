"""Varied wording for the lines code writes, so Mia doesn't say the same sentence twice.

Belinda, 2026-11-11 (call fa3b77253965): the read-back, "Give me one second while I calculate
your quote" and the representative offer came out word for word twice in one call. Each line
here has three wordings; ``pick`` chooses one at random, never the one this call used last time,
and keeps its choice for the rest of the caller's turn (the read-back is built more than once
per turn, and every copy must be the same sentence).

Every wording must keep what code looks for in it: a read-back says "ship" and ends with "is
that correct/right?" or "does that sound right?" (guardrails._READ_BACK); an offer says
"connect" or "representative" (grounding.offered_person); a closing ends with a goodbye
(guardrails.is_goodbye).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import Any

# Tests replace this with a deterministic choice (tests/conftest.py).
choose: Callable[[Sequence[str]], str] = random.choice

READ_BACK = (
    "Just to confirm, {vehicles} will ship from {origin} to {destination}. Is that correct?",
    "Let me make sure I have it right: {vehicles} will ship from {origin} to {destination}. "
    "Is that right?",
    "So that's {vehicles}, shipping from {origin} to {destination}. Does that sound right?",
)

FILLER = (
    "Give me one second while I calculate your quote.",
    "One moment while I get your price.",
    "Let me run the numbers for you, just a second.",
)

OFFER = (
    "Would you like me to connect you with a licensed representative who can assist you further?",
    "I can connect you with a licensed representative to go over the details. Would you like that?",
    "Would you like to speak with a licensed representative about next steps?",
)

CLOSING = (
    "Thanks for calling F&F! Feel free to call us again if you'd like another quote. Have a "
    "nice day!",
    "Thank you for calling F&F. If you ever need another quote, just give us a call. Have a "
    "great day!",
    "Thanks so much for calling F&F! We're here whenever you need another quote. Take care!",
)


def pick(state: Any, key: str, options: Sequence[str]) -> str:
    """One of ``options`` for this call: the same one all through a caller turn, a different
    one from last time on the next turn."""
    turn = getattr(state, "caller_turns", 0)
    used = state.phrases.get(key)
    if used and used[0] == turn:
        return used[1]
    last = used[1] if used else None
    chosen = choose([o for o in options if o != last] or list(options))
    state.phrases[key] = (turn, chosen)
    return chosen
