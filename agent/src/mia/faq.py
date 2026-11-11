"""FAQ answers, checked in code (docs/CONVERSATION_DESIGN.md, "FAQs").

The model answers FAQs from the prompt, but not always with the fact that matters: in the
stage 7 simulations "Can I leave some boxes in the trunk?" got "Sure." and a payment question
got the card fee without "cash on delivery". Like prices, the facts come from code: when the
caller asked one of these and Mia's line lacks its key fact, ``ensure_answer`` puts the
canonical answer first and keeps her question (keep_going adds one if there isn't any).

Each entry (first match wins, so "deposit" comes before "payment": both say "pay"): what the
caller says (regex), the key fact (every group needs one of its words in
Mia's line), and the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mia import grounding
from mia.guardrails import _READ_BACK


@dataclass(frozen=True)
class Faq:
    topic: str
    asked: re.Pattern[str]
    key: tuple[tuple[str, ...], ...]
    answer: str


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


FAQS = (
    Faq(
        "enclosed",
        # "a closed shipping" is how STT heard "enclosed" (live check, 2026-11-10).
        _re(r"\benclosed\b|\bclosed\b.{0,20}\b(?:ship\w*|transport\w*|trailer|carrier)\b"),
        (("open",),),
        "We only quote open car shipping.",
    ),
    Faq(
        "personal_items",
        _re(
            r"\b(?:boxes|stuff|things|items|belongings|luggage|bags|personal)\b.{0,40}"
            r"\b(?:trunk|car|inside|in it|vehicle)\b|\bleave .{0,20}\bin the (?:trunk|car)\b"
        ),
        (("100", "hundred"),),
        "The quote includes up to 100 pounds in the trunk, below window level. More than that "
        "costs extra, and a licensed representative can help with the details.",
    ),
    Faq(
        "deposit",
        _re(r"\b(?:deposit|up ?front|upfront|pay (?:it )?(?:all )?(?:now|ahead|in advance))\b"),
        (("4", "four"),),
        "Paying a deposit upfront takes off about 4 percent; a licensed representative confirms "
        "the exact amount.",
    ),
    Faq(
        "payment",
        # How they pay, not how much ("how much will I pay?" is the quote).
        # A bare "card" isn't enough: speech-to-text hears "car" as "card" (call 9ea951ab02c2,
        # 2026-11-11: "I want to change one card" got the payment answer). It needs a payment
        # word next to it, or "credit/debit card", or "take/accept cards".
        _re(
            r"\bpay (?:with|by|in|using|on)\b|\bpayment (?:options?|methods?)\b|"
            r"\b(?:credit|debit) ?cards?\b|\bcash\b|"
            r"\b(?:pay|paying|payment)\b[^.?!]{0,30}\bcards?\b|"
            r"\bcards?\b[^.?!]{0,20}\b(?:fees?|payments?|pay)\b|"
            r"\b(?:take|takes|accept|accepts)\s+(?:credit\s+)?cards?\b"
        ),
        (("cash",), ("3", "three")),
        "The quote is for cash on delivery; a credit card may add about 3 percent.",
    ),
    Faq(
        "modified",
        _re(r"\b(?:modified|lifted|lowered|aftermarket|mods)\b"),
        (("300", "three hundred"),),
        "A modified vehicle is about 300 dollars extra; a licensed representative confirms.",
    ),
)


def asked_about(text: str) -> Faq | None:
    """The FAQ the caller's message asks about, if it's a question about one. The topic must be
    in the question itself, not elsewhere in the message: "Can we actually... I made a mistake.
    I want to change one card." asks to change a car, not how to pay (call 9ea951ab02c2)."""
    question = grounding.question_part(text)
    if not question:
        return None
    for faq in FAQS:
        if faq.asked.search(question):
            return faq
    return None


def _has_key(spoken: str, faq: Faq) -> bool:
    low = spoken.lower()
    return all(any(w in low for w in group) for group in faq.key)


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def ensure_answer(spoken: str, last_said: str) -> str:
    """Mia's line, with the canonical FAQ answer first if hers lacks the key fact. Her question
    (the last sentence ending in "?") is kept, so the quote moves on."""
    faq = asked_about(last_said)
    if faq is None or (spoken and _has_key(spoken, faq)) or "$" in spoken:
        return spoken  # a line with a price is the quote: never rewritten
    if _READ_BACK.search(spoken):
        # The car and a question in one message: the answer, then the whole read-back
        # (scenario acknowledge_and_answer, 2026-11-11).
        return f"{faq.answer} {spoken}"
    sentences = [s for s in _SENTENCE.split(spoken.strip()) if s]
    question = next((s for s in reversed(sentences) if s.endswith("?")), "")
    return f"{faq.answer} {question}".strip()
