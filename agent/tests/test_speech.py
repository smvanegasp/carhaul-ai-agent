"""Numbers written out for the voice (mia/speech.py)."""

import pytest

from mia.speech import for_tts


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        (
            "Your estimated cost is $1,191.",
            "Your estimated cost is one thousand, one hundred ninety-one dollars.",
        ),
        ("It's $724.", "It's seven hundred twenty-four dollars."),
        ("$1 even", "one dollar even"),
        ("$12.50 extra", "twelve dollars and fifty cents extra"),
        ("a 2020 Toyota Camry", "a twenty twenty Toyota Camry"),
        ("a 2005 Honda", "a two thousand five Honda"),
        ("a 1998 Ford", "a nineteen ninety-eight Ford"),
        ("3 to 6 days door to door", "three to six days door to door"),
        ("ZIP 02110 in Boston", "ZIP zero two one one zero in Boston"),
        ("Two cars: $1,300 total", "Two cars: one thousand, three hundred dollars total"),
        ("No numbers here.", "No numbers here."),
    ],
)
def test_numbers_become_words(text, spoken):
    assert for_tts(text) == spoken


def test_a_price_that_looks_like_a_year_is_still_money():
    assert for_tts("$2,020") == "two thousand twenty dollars"
