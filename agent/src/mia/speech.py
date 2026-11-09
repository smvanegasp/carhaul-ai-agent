"""Text Mia speaks, prepared for the voice: numbers become words.

Voices read digits their own way and fast ("$1,191" came out rushed on Sergio's first calls,
2026-11-09), and each provider differently. So before any text reaches the TTS (``Mia.tts_node``)
numbers are written out the way a person says them, the same for every voice:

- ``$1,191`` → "one thousand, one hundred ninety-one dollars" (the comma is a natural pause)
- model years ``2020`` → "twenty twenty", ``2005`` → "two thousand five"
- ZIP codes ``02110`` → "zero two one one zero"
- other whole numbers → words ("3 to 6 days" → "three to six days")

The transcript the caller sees keeps the digits (LiveKit transcribes the text before this step).
"""

from __future__ import annotations

import re

from num2words import num2words

_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")
_YEAR = re.compile(r"(?<![\d,.$])(19\d{2}|20\d{2})(?![\d,])")
_ZIP = re.compile(r"(?<![\d,.$])(\d{5})(?![\d,])")
_NUMBER = re.compile(r"(?<![\d.$])(\d{1,3}(?:,\d{3})+|\d+)(?![\d])")

_DIGITS = "zero one two three four five six seven eight nine".split()


def _words(n: int) -> str:
    # US style: "one hundred ninety-one", not "one hundred and ninety-one".
    return num2words(n).replace(" and ", " ")


def _money(m: re.Match[str]) -> str:
    dollars = int(m.group(1).replace(",", ""))
    text = f"{_words(dollars)} dollar{'s' if dollars != 1 else ''}"
    cents = int(m.group(2) or 0)
    if cents:
        text += f" and {_words(cents)} cent{'s' if cents != 1 else ''}"
    return text


def _year(m: re.Match[str]) -> str:
    return num2words(int(m.group(1)), to="year").replace(" and ", " ")


def _zip(m: re.Match[str]) -> str:
    return " ".join(_DIGITS[int(d)] for d in m.group(1))


def _number(m: re.Match[str]) -> str:
    return _words(int(m.group(1).replace(",", "")))


def for_tts(text: str) -> str:
    """``text`` with every number written out for the voice (see module docstring)."""
    text = _MONEY.sub(_money, text)
    text = _YEAR.sub(_year, text)
    text = _ZIP.sub(_zip, text)
    return _NUMBER.sub(_number, text)
