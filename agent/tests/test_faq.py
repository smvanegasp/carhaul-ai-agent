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


def test_a_question_with_the_car_keeps_the_read_back():
    # "It's a 2025 Honda Civic. Oh, and do you do enclosed shipping?" -> the answer was lost.
    read_back = (
        "Just to confirm, your 2025 Honda Civic will ship from Boston, Massachusetts to San "
        "Francisco, California. Is that correct?"
    )
    out = faq.ensure_answer(read_back, "It's a Civic. Oh, and do you do enclosed shipping?")
    assert out == f"We only quote open car shipping. {read_back}"


# Call 9ea951ab02c2 (2026-11-11): speech-to-text heard "car" as "card", in a message that also
# asked something; Mia answered how to pay, which nobody asked.
@pytest.mark.parametrize(
    "said",
    [
        "Yes. Can we actually I think I made a mistake. I want to change one card. I I no longer "
        "need the Jeep. I want to better send my twenty twenty four Honda.",
        "Can you change the second card to a Honda?",
        "Is the card going to be picked up at my house?",
    ],
)
def test_card_misheard_for_car_isnt_a_payment_question(said):
    assert faq.asked_about(said) is None


@pytest.mark.parametrize(
    "said",
    [
        "Do you take credit cards?",
        "Can I pay with a card?",
        "Is there a fee if I pay by card?",
        "Do you accept cards?",
        "What payment methods do you have?",
        "I'm moving to Boston. Can I pay cash?",
    ],
)
def test_real_payment_questions_still_count(said):
    found = faq.asked_about(said)
    assert found is not None and found.topic == "payment"


def test_the_topic_must_be_in_the_question():
    # Enclosed said outside the question isn't asked about...
    assert faq.asked_about("I don't need enclosed. How long does it take?") is None
    # ...but "I want to know if" carries the rest of its sentence.
    said = "I want to know if you offer enclosed like, shippings, and I'm sending my car to Miami."
    assert faq.asked_about(said).topic == "enclosed"
