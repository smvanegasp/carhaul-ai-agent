"""FAQ answers checked in code (faq.py)."""

from __future__ import annotations

import pytest

from mia import faq


@pytest.mark.parametrize(
    "asked, topic",
    [
        ("Do you do enclosed shipping?", "enclosed"),
        ("do you do a closed shipping?", "enclosed"),
        ("Can I leave some boxes in the trunk?", "personal_items"),
        ("Can I put my stuff inside the car?", "personal_items"),
        ("Can I pay with a credit card?", "payment"),
        ("Is there a discount if I pay a deposit upfront?", "deposit"),
        ("It's lifted, is that a problem?", "modified"),
        ("From Boston to San Francisco", None),
        ("How much will I pay?", None),  # that's the quote
        ("Is that covered by insurance?", None),
        ("Are you closed on Sundays?", None),
        ("I'll pay with a card.", None),  # not a question
        ("It's a 2020 Honda Civic", None),
    ],
)
def test_asked_about(asked, topic):
    found = faq.asked_about(asked)
    assert (found.topic if found else None) == topic


def test_a_missing_fact_gets_the_canonical_answer_and_keeps_the_question():
    # Stage 7 simulation: "Can I leave some boxes in the trunk?" -> "Sure. What year, make..."
    out = faq.ensure_answer(
        "Sure. What year, make and model is the car?", "Can I leave boxes in the trunk?"
    )
    assert out.startswith("The quote includes up to 100 pounds in the trunk")
    assert out.endswith("What year, make and model is the car?")


def test_a_right_answer_is_left_alone():
    said = "Paying cash on delivery is the quoted price; a card adds about 3 percent. What car?"
    assert faq.ensure_answer(said, "Can I pay with a credit card?") == said
    other = "Great. Where is it going?"
    assert faq.ensure_answer(other, "From Boston") == other


def test_a_price_line_is_never_rewritten():
    line = "Your estimated cost is $1,291. Would you like me to connect you?"
    assert faq.ensure_answer(line, "Can I pay with a credit card?") == line
